"""
main.py — Batch driver for presence-condition (PC) extraction.

This script reads an input CSV with columns:
    Project, File, Caller, Callee

For each row, it:
  1) Resolves the C source path inside the local `projects/` directory.
  2) Loads the file contents.
  3) Extracts the presence condition(s) under which `callee` is called inside `caller`.
  4) Writes the output CSV with an additional `PC` column.

Output schema:
    Project, File, Caller, Callee, PC

Notes
-----
- If a call site is not under any preprocessor condition, PC must be "TRUE".
- If the file cannot be located, PC is "FILE_NOT_FOUND".
- If the caller function cannot be located, PC is "CALLER_NOT_FOUND".
- If the callee call cannot be located inside the caller bounds, PC is "CALL_NOT_FOUND".
"""

from __future__ import annotations

import argparse
import logging
import os
from functools import lru_cache
from typing import Dict, List, Tuple

import pandas as pd

from CSVHandler import CSVHandler
from PresenceConditionExtractor import PresenceConditionExtractor
from SourceCodeAnalyzer import SourceCodeAnalyzer

# -----------------------------------------------------------------------------
# Logging
# -----------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# -----------------------------------------------------------------------------
# Path normalization & resolution

def _is_regular_file(path: str) -> bool:
    """Return True iff `path` exists and is a regular file (not a directory)."""
    try:
        return os.path.isfile(path)
    except OSError:
        return False

# -----------------------------------------------------------------------------
def _normalize_csv_path(path_str: str) -> str:
    """
    Normalize a path string from the CSV.

    Steps:
      - Trim whitespace.
      - Convert backslashes to forward slashes.
      - Remove leading './' segments.
      - Preserve leading '/' to keep absolute-path semantics.
    """
    if path_str is None:
        return ""
    p = str(path_str).strip().replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p


@lru_cache(maxsize=256)
def _build_project_index(project_root: str, exts: Tuple[str, ...] = (".c",)) -> Dict[str, List[str]]:
    """
    Build an index of all source files under `project_root`, keyed by basename.

    Example:
      index["multi.c"] -> ["/.../curl/lib/multi.c", "/.../curl/tests/multi.c", ...]

    This index is a *fallback* when direct path joins fail (layout divergence).
    """
    index: Dict[str, List[str]] = {}
    if not os.path.isdir(project_root):
        return index

    for root, _, files in os.walk(project_root):
        for fname in files:
            if any(fname.endswith(ext) for ext in exts):
                full = os.path.join(root, fname)
                index.setdefault(fname, []).append(full)
    return index


def _best_suffix_match(candidates: List[str], desired_rel_like: str) -> str:
    """
    Select the candidate path whose suffix (path components from the end)
    matches the desired CSV path with the greatest overlap.
    """
    if not candidates:
        return ""

    desired = desired_rel_like.replace("\\", "/").strip("/")

    def score(path: str) -> int:
        comps_a = path.replace("\\", "/").split("/")
        comps_b = desired.split("/")
        i = 1
        while i <= min(len(comps_a), len(comps_b)) and comps_a[-i] == comps_b[-i]:
            i += 1
        return i - 1

    return max(candidates, key=score)


def resolve_source_path(projects_dir: str, project: str, file_field: str) -> str:
    """
    Resolve the absolute filesystem path for a source file described by the CSV.

    The input CSV is often inconsistent across datasets:
      - Some rows store File="lib/multi.c"
      - Others store File="curl/lib/multi.c"
      - Some datasets include deeper nesting due to repository layout changes.

    Resolution strategy (in order):
      1) If `File` is absolute, accept it if it exists.
      2) Try: projects_dir / project / File
      3) Try: projects_dir / File
      4) If File starts with "<project>/", also try: projects_dir / project / File
         (this covers layouts like projects/curl/curl/...).
      5) Fallback: basename search inside projects_dir/project, best suffix match.

    Returns:
      Absolute path if found, else "".
    """
    ff = _normalize_csv_path(file_field)
    project = str(project).strip()

    if not ff:
        return ""

    # (1) Absolute
    if os.path.isabs(ff):
        return ff if _is_regular_file(ff) else ""

    # Candidate list (keep order: most plausible first)
    candidates: List[str] = []

    # (2) projects_dir / project / ff  (typical)
    candidates.append(os.path.join(projects_dir, project, ff))

    # (3) projects_dir / ff  (File already includes project prefix)
    candidates.append(os.path.join(projects_dir, ff))

    # (4) If ff already starts with "<project>/", attempt double nesting:
    #     projects/curl/curl/...
    first_comp = ff.split("/")[0]
    if first_comp == project:
        candidates.append(os.path.join(projects_dir, project, ff))

    for p in candidates:
        if _is_regular_file(p):
            return p

    # (5) Fallback: search by basename within the project directory
    project_root = os.path.join(projects_dir, project)
    index = _build_project_index(project_root, exts=(".c",))
    tail = os.path.basename(ff)
    cands = index.get(tail, [])
    if cands:
        best = _best_suffix_match(cands, ff)
        if best and _is_regular_file(best):
            logging.warning(f"[PathResolver] Fallback matched by suffix: '{ff}' → '{best}'")
            return best

    return ""


# -----------------------------------------------------------------------------
# Main pipeline
# -----------------------------------------------------------------------------
def _repo_root_from_this_file() -> str:
    """Return repository root as: <root>/source/main.py -> <root>."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))


def _default_paths() -> Tuple[str, str, str]:
    """
    Compute robust default paths relative to the repository root:

      <root>/projects
      <root>/output
      <root>/projects_cs.csv  (if you keep it in root)
      or <root>/source/projects_cs.csv (if you keep it in source)
    """
    root = _repo_root_from_this_file()

    projects_dir = os.path.join(root, "projects")
    output_dir = os.path.join(root, "output")

    # Prefer root/projects_cs.csv; fallback to source/projects_cs.csv
    input_csv_root = os.path.join(root, "cs_projects.csv")
    input_csv_source = os.path.join(root, "source", "cs_projects.csv")
    input_csv = input_csv_root if os.path.exists(input_csv_root) else input_csv_source

    return input_csv, projects_dir, output_dir


def _is_pseudo_callee(callee: str) -> bool:
    """
    Heuristic filter for CSV noise.

    - `defined` appears when the upstream call extractor mistakenly treats
      `defined(MACRO)` as a call target.
    - Empty callee fields are also possible in noisy datasets.
    """
    if not callee:
        return True
    return callee.strip().lower() in {"defined"}


def main() -> None:
    input_csv_default, projects_dir_default, output_dir_default = _default_paths()

    parser = argparse.ArgumentParser(description="Extract presence conditions for caller→callee pairs.")
    parser.add_argument("--input", default=input_csv_default, help="Input CSV with Project,File,Caller,Callee.")
    parser.add_argument("--projects", default=projects_dir_default, help="Directory containing all projects.")
    parser.add_argument("--output", default=os.path.join(output_dir_default, "cs_projects__with_pc.csv"),
                        help="Output CSV path.")
    args = parser.parse_args()

    input_csv_path = args.input
    projects_dir = args.projects
    output_csv_path = args.output

    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    logging.info(f"Input CSV: {input_csv_path}")
    logging.info(f"Projects dir: {projects_dir}")
    logging.info(f"Output CSV: {output_csv_path}")

    csv_handler = CSVHandler(input_csv_path)
    df = csv_handler.load_csv()

    required_cols = ["Project", "File", "Caller", "Callee"]
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Missing required column in CSV: {col}")

    # Initialize output column
    df["PC"] = "UNDEFINED"

    # Drop pseudo-callee noise early (keeps output cleaner and faster)
    before_drop = len(df)
    df = df[~df["Callee"].astype(str).map(_is_pseudo_callee)].copy()
    df.reset_index(drop=True, inplace=True)
    if len(df) != before_drop:
        logging.info(f"Dropped {before_drop - len(df)} pseudo-callee/noise rows.")

    # Cache loaded source code per absolute file path (big speedup in large datasets)
    source_cache: Dict[str, str] = {}

    # Cache extraction results per (abs_path, caller, callee)
    pc_cache: Dict[Tuple[str, str, str], List[str]] = {}

    # Collect extra rows when a caller contains multiple call sites for the same callee
    extra_rows: List[pd.Series] = []

    for idx, row in df.iterrows():
        project = str(row["Project"]).strip()
        file_field = str(row["File"]).strip()
        caller = str(row["Caller"]).strip()
        callee = str(row["Callee"]).strip()

        abs_path = resolve_source_path(projects_dir, project, file_field)
        logging.info(f"Processing file: {abs_path or '[NOT FOUND]'}, Caller: {caller}, Callee: {callee}")

        if not abs_path or not _is_regular_file(abs_path):
            logging.error(f"File not found (after resolution attempts): {project} :: {file_field}")
            df.at[idx, "PC"] = "FILE_NOT_FOUND"
            continue

        # Load source (cached)
        if abs_path not in source_cache:
            try:
                analyzer = SourceCodeAnalyzer(abs_path)
            except IsADirectoryError:
                logging.error(f"Path is a directory (skipping): {abs_path}")
                df.at[idx, "PC"] = "FILE_NOT_FOUND"
                continue
            source_cache[abs_path] = analyzer.source_code

        cache_key = (abs_path, caller, callee)
        if cache_key not in pc_cache:
            extractor = PresenceConditionExtractor(source_cache[abs_path])
            pcs = extractor.extract_pc_from_caller_context(caller, callee)
            if isinstance(pcs, str):
                pcs = [pcs]
            if not pcs:
                pcs = ["CALL_NOT_FOUND"]
            pc_cache[cache_key] = pcs

        pcs = pc_cache[cache_key]

        # First PC in the original row
        df.at[idx, "PC"] = pcs[0]

        # Remaining PCs become additional rows
        for pc in pcs[1:]:
            new_row = row.copy()
            new_row["PC"] = pc
            extra_rows.append(new_row)

    # Append extra rows (multi-call expansion)
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    # De-duplicate final output
    df.drop_duplicates(subset=["Project", "File", "Caller", "Callee", "PC"], inplace=True, keep="first")
    df.reset_index(drop=True, inplace=True)

    csv_handler.dataframe = df
    csv_handler.save_csv(output_csv_path)

    logging.info("Extraction completed successfully.")


if __name__ == "__main__":
    main()