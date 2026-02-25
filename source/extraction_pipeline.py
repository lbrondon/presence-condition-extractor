from __future__ import annotations

import logging
from typing import Dict, List, Tuple

import pandas as pd

from PresenceConditionExtractor import PresenceConditionExtractor
from SourceCodeAnalyzer import SourceCodeAnalyzer
from path_resolver import is_regular_file, resolve_source_path


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


def run_extraction_pipeline(df: pd.DataFrame, projects_dir: str) -> pd.DataFrame:
    """
    Execute the batch PC extraction over a normalized input DataFrame.

    Expected input columns:
      Project, File, Caller, Callee

    Returns:
      A new DataFrame with a populated `PC` column, preserving the current
      status/error semantics and multi-call expansion behavior.
    """
    required_cols = ["Project", "File", "Caller", "Callee"]
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Missing required column in CSV: {col}")

    # Work on a copy to avoid mutating the caller's DataFrame unexpectedly.
    df = df.copy()

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

    # Cache parsed extractors per absolute file path (avoids rebuilding indices/PC maps)
    extractor_cache: Dict[str, PresenceConditionExtractor] = {}

    # Cache extraction results per (abs_path, caller, callee)
    pc_cache: Dict[Tuple[str, str, str], List[str]] = {}

    # Collect extra rows when a caller contains multiple call sites for the same callee
    extra_rows: List[pd.Series] = []

    for idx, project_raw, file_raw, caller_raw, callee_raw in df[
        ["Project", "File", "Caller", "Callee"]
    ].itertuples(index=True, name=None):
        project = str(project_raw).strip()
        file_field = str(file_raw).strip()
        caller = str(caller_raw).strip()
        callee = str(callee_raw).strip()

        abs_path = resolve_source_path(projects_dir, project, file_field)
        logging.info(f"Processing file: {abs_path or '[NOT FOUND]'}, Caller: {caller}, Callee: {callee}")

        if not abs_path or not is_regular_file(abs_path):
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
            if abs_path not in extractor_cache:
                extractor_cache[abs_path] = PresenceConditionExtractor(source_cache[abs_path])
            extractor = extractor_cache[abs_path]
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
            new_row = df.loc[idx].copy()
            new_row["PC"] = pc
            extra_rows.append(new_row)

    # Append extra rows (multi-call expansion)
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    # De-duplicate final output
    df.drop_duplicates(subset=["Project", "File", "Caller", "Callee", "PC"], inplace=True, keep="first")
    df.reset_index(drop=True, inplace=True)

    return df
