from __future__ import annotations

import logging
import os
from functools import lru_cache
from typing import Dict, List, Tuple


def is_regular_file(path: str) -> bool:
    """Return True iff `path` exists and is a regular file (not a directory)."""
    try:
        return os.path.isfile(path)
    except OSError:
        return False


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
        return ff if is_regular_file(ff) else ""

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
        if is_regular_file(p):
            return p

    # (5) Fallback: search by basename within the project directory
    project_root = os.path.join(projects_dir, project)
    index = _build_project_index(project_root, exts=(".c",))
    tail = os.path.basename(ff)
    cands = index.get(tail, [])
    if cands:
        best = _best_suffix_match(cands, ff)
        if best and is_regular_file(best):
            logging.warning(f"[PathResolver] Fallback matched by suffix: '{ff}' → '{best}'")
            return best

    return ""
