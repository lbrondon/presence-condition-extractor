"""
Main entry point for batch extraction of presence conditions (PCs).

This script:
  1) Loads (Project, File, Caller, Callee) tuples from a CSV.
  2) Resolves each source path robustly against the local projects tree.
  3) Parses the corresponding C file and extracts the presence condition(s)
     under which the given callee is invoked inside the specified caller.
  4) Emits the results to a CSV, expanding rows when multiple call sites exist.

Design notes:
  • Path resolution is intentionally defensive (handles absolute/relative
    paths, slashes, and slightly diverging layouts), with a final fallback
    based on suffix matching within a project tree.
  • The pipeline tolerates duplicates in the input CSV; it de-duplicates
    output rows by (Project, File, Caller, Callee, PC).
  • “Pseudo-callees” such as `defined` (not real function calls) are dropped.
"""

from CSVHandler import CSVHandler
from SourceCodeAnalyzer import SourceCodeAnalyzer
from PresenceConditionExtractor import PresenceConditionExtractor

import os
import logging
import pandas as pd
from functools import lru_cache

# ---------------------------------------------------------------------------
# Logging configuration
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# ---------------------------------------------------------------------------
# Path utilities
# ---------------------------------------------------------------------------
def _normalize_csv_path(path_str: str) -> str:
    """
    Normalize a path value coming from CSV.

    Behavior:
      - Trims whitespace.
      - Converts backslashes to forward slashes.
      - Removes leading './' segments.
      - Leaves a leading '/' intact to preserve absolute-path semantics.

    Parameters
    ----------
    path_str : str
        Raw path string from the CSV.

    Returns
    -------
    str
        Normalized path string (may be empty when input is None).
    """
    if path_str is None:
        return ""
    p = str(path_str).strip().replace('\\', '/')
    while p.startswith('./'):
        p = p[2:]
    if p.startswith('/'):
        # Keep leading '/' so that POSIX absolute paths remain recognizable.
        return p
    return p


@lru_cache(maxsize=256)
def _build_project_index(project_root: str):
    """
    Build a lightweight index of all .c files under a project directory.

    The index maps a basename (e.g., 'foo.c') to a list of absolute paths for
    files with that name. Used as a last-resort fallback when straightforward
    joins fail to locate a source file.

    Parameters
    ----------
    project_root : str
        Absolute path to the project root directory.

    Returns
    -------
    dict[str, list[str]]
        Mapping from filename to candidate absolute paths.
    """
    index = {}
    if not os.path.isdir(project_root):
        return index
    for root, _, files in os.walk(project_root):
        for f in files:
            # Restrict to .c files; adjust if you need to cover headers or other extensions.
            if f.endswith('.c'):
                full = os.path.join(root, f)
                index.setdefault(f, []).append(full)
    return index


def _best_suffix_match(candidates, desired_rel_like: str) -> str:
    """
    Choose the candidate whose suffix best matches the desired relative path.

    Rationale
    ---------
    When a CSV path slightly diverges from the actual layout (e.g., additional
    directories, renamed roots), a longest-common-suffix match over path
    components is robust in practice.

    Parameters
    ----------
    candidates : list[str]
        Absolute paths discovered in the project index for a given basename.
    desired_rel_like : str
        The 'desired' path (as it appears in the CSV), treated as a relative-like string.

    Returns
    -------
    str
        The best-matching absolute path (empty string when no candidates).
    """
    if not candidates:
        return ""
    desired = desired_rel_like.replace('\\', '/').strip('/')

    def score(path: str) -> int:
        comps_a = path.replace('\\', '/').split('/')
        comps_b = desired.split('/')
        i = 1
        while i <= min(len(comps_a), len(comps_b)) and comps_a[-i] == comps_b[-i]:
            i += 1
        return i - 1  # number of equal components from the end

    return max(candidates, key=score)


def resolve_source_path(base_dir: str, project: str, file_field: str) -> str:
    """
    Resolve an absolute filesystem path for a source file using robust rules:

      1) If `file_field` is absolute, return it when it exists.
      2) If `file_field` starts with the project name, join as base_dir / file_field.
      3) Otherwise try base_dir / project / file_field.
      4) Try base_dir / file_field (for CSVs that already include 'project/').
      5) Fallback: search by basename within base_dir/project and pick
         the best suffix match.

    Parameters
    ----------
    base_dir : str
        Absolute path to the root directory containing projects.
    project : str
        Project ID/name (used in path reconstruction and fallback search).
    file_field : str
        Path string from the CSV's 'File' column.

    Returns
    -------
    str
        Resolved absolute path, or empty string when not found.
    """
    ff = _normalize_csv_path(file_field)

    # Absolute path?
    if os.path.isabs(ff):
        return ff if os.path.exists(ff) else ""

    # If CSV already starts with the project name, do not duplicate it
    first_comp = ff.split('/')[0] if ff else ""
    if first_comp == project:
        p = os.path.join(base_dir, ff)
        if os.path.exists(p):
            return p

    # Try base_dir / project / ff
    p = os.path.join(base_dir, project, ff)
    if os.path.exists(p):
        return p

    # Try base_dir / ff (CSV may already include 'project/')
    p = os.path.join(base_dir, ff)
    if os.path.exists(p):
        return p

    # Fallback: index & suffix match within the project
    project_root = os.path.join(base_dir, project)
    index = _build_project_index(project_root)
    tail = os.path.basename(ff)
    cands = index.get(tail, [])
    if cands:
        best = _best_suffix_match(cands, ff)
        if best and os.path.exists(best):
            logging.warning(f"[PathResolver] Fallback matched by suffix: '{ff}' → '{best}'")
            return best

    # Not found
    return ""


# ---------------------------------------------------------------------------
# Batch driver
# ---------------------------------------------------------------------------
def main():
    """
    Batch driver that orchestrates:
      • CSV loading and validation,
      • path resolution for each row,
      • PC extraction for (caller, callee) pairs,
      • multi-call expansion and de-duplication,
      • and final CSV persistence.
    """
    input_csv_path = 'projects_cs.csv'  # adjust as needed for your dataset
    base_directory = '/home/lucas/Documents/presence_condition_extractor/projects'
    output_csv_path = '/home/lucas/Documents/presence_condition_extractor/output/projects_with_pc.csv'

    logging.info(f"Starting CSV processing: {input_csv_path}")
    csv_handler = CSVHandler(input_csv_path)
    df = csv_handler.load_csv()

    # Validate required columns early to fail fast on malformed inputs.
    for col in ['Project', 'File', 'Caller', 'Callee']:
        if col not in df.columns:
            raise KeyError(f"Missing required column in CSV: {col}")

    # Initialize output column with a sentinel.
    df['PC'] = 'UNDEFINED'

    # (1) Filter out pseudo-callees (e.g., 'defined'), which are not real calls.
    to_drop_idx = []
    PSEUDO_CALLEES = {'defined'}  # extend if needed
    for idx, row in df.iterrows():
        callee = str(row['Callee']).strip()
        if callee.lower() in PSEUDO_CALLEES:
            to_drop_idx.append(idx)
    if to_drop_idx:
        logging.info(f"Dropping {len(to_drop_idx)} pseudo-callee rows (e.g., 'defined').")
        df.drop(index=to_drop_idx, inplace=True)
        df.reset_index(drop=True, inplace=True)

    # (2) Caches to avoid recomputation and duplicate emission
    result_cache = {}   # (project, abs_path, caller, callee) -> List[str]
    emitted_keys = set()
    extra_rows = []     # additional rows for multiple call sites

    # Main extraction loop
    for idx, row in df.iterrows():
        project = str(row['Project']).strip()
        file_name = str(row['File']).strip()
        caller = str(row['Caller']).strip()
        callee = str(row['Callee']).strip()

        abs_path = resolve_source_path(base_directory, project, file_name)
        logging.info(f"Processing file: {abs_path or '[NOT FOUND]'}, Caller: {caller}, Callee: {callee}")

        if not abs_path or not os.path.exists(abs_path):
            logging.error(f"File not found (after resolution attempts): {project} :: {file_name}")
            df.at[idx, 'PC'] = 'FILE_NOT_FOUND'
            continue

        key = (project, abs_path, caller, callee)

        # If we already emitted this (Project, Path, Caller, Callee), mark this row to drop later.
        if key in emitted_keys:
            df.at[idx, 'PC'] = '__DUP_TO_DROP__'
            continue

        # Compute (or reuse) PCs for this key.
        try:
            if key not in result_cache:
                analyzer = SourceCodeAnalyzer(abs_path)
                extractor = PresenceConditionExtractor(analyzer.source_code)
                pcs = extractor.extract_pc_from_caller_context(caller, callee)
                if isinstance(pcs, str):
                    pcs = [pcs]
                if not pcs:
                    pcs = ['CALL_NOT_FOUND']
                result_cache[key] = pcs
            else:
                pcs = result_cache[key]

            emitted_keys.add(key)

            # Place the first PC on the current row
            df.at[idx, 'PC'] = pcs[0]
            logging.info(f"{caller} → {callee} → PC[0]: {pcs[0]}")

            # Emit additional PCs (when multiple call sites exist) as synthetic rows
            for extra_pc in pcs[1:]:
                new_row = row.copy()
                new_row['PC'] = extra_pc
                extra_rows.append(new_row)
                logging.info(f"{caller} → {callee} → PC[extra]: {extra_pc}")

        except FileNotFoundError:
            logging.error(f"File not found while reading: {abs_path}")
            df.at[idx, 'PC'] = 'FILE_NOT_FOUND'
        except Exception as e:
            logging.exception(f"Error processing file {abs_path}: {e}")
            df.at[idx, 'PC'] = f'ERROR: {str(e)}'

    # Drop “already emitted” placeholders
    if '__DUP_TO_DROP__' in df['PC'].values:
        df = df[df['PC'] != '__DUP_TO_DROP__'].copy()

    # Append extra rows (multi-call expansion) and de-duplicate final output
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    before = len(df)
    df.drop_duplicates(subset=['Project', 'File', 'Caller', 'Callee', 'PC'], inplace=True, keep='first')
    df.reset_index(drop=True, inplace=True)
    after = len(df)
    if after != before:
        logging.info(f"Drop duplicates: {before - after} rows removed")

    # Persist results
    csv_handler.dataframe = df
    csv_handler.save_csv(output_csv_path)
    logging.info(f"Processing completed. Output saved to: {output_csv_path}")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
