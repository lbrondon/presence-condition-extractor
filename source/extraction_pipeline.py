from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Dict, List, Tuple

import pandas as pd

from PresenceConditionExtractor import PresenceConditionExtractor
from SourceCodeAnalyzer import SourceCodeAnalyzer
from path_resolver import is_regular_file, resolve_source_path


@dataclass(frozen=True)
class _ExtractionRequest:
    idx: int
    project: str
    file_field: str
    caller: str
    callee: str


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


def _validate_input_df(df: pd.DataFrame) -> None:
    required_cols = ["Project", "File", "Caller", "Callee"]
    for col in required_cols:
        if col not in df.columns:
            raise KeyError(f"Missing required column in CSV: {col}")


def _prepare_input_df(df: pd.DataFrame) -> pd.DataFrame:
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

    return df


def _get_cached_pcs(
    abs_path: str,
    caller: str,
    callee: str,
    source_cache: Dict[str, str],
    extractor_cache: Dict[str, PresenceConditionExtractor],
    pc_cache: Dict[Tuple[str, str, str], List[str]],
) -> List[str]:
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
    return pc_cache[cache_key]


def _finalize_output_df(df: pd.DataFrame, extra_rows: List[pd.Series]) -> pd.DataFrame:
    # Append extra rows (multi-call expansion)
    if extra_rows:
        df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    # De-duplicate final output
    df.drop_duplicates(subset=["Project", "File", "Caller", "Callee", "PC"], inplace=True, keep="first")
    df.reset_index(drop=True, inplace=True)
    return df


def _iter_requests(df: pd.DataFrame):
    for idx, project_raw, file_raw, caller_raw, callee_raw in df[
        ["Project", "File", "Caller", "Callee"]
    ].itertuples(index=True, name=None):
        yield _ExtractionRequest(
            idx=idx,
            project=str(project_raw).strip(),
            file_field=str(file_raw).strip(),
            caller=str(caller_raw).strip(),
            callee=str(callee_raw).strip(),
        )


def _process_request(
    req: _ExtractionRequest,
    df: pd.DataFrame,
    projects_dir: str,
    source_cache: Dict[str, str],
    extractor_cache: Dict[str, PresenceConditionExtractor],
    pc_cache: Dict[Tuple[str, str, str], List[str]],
    extra_rows: List[pd.Series],
) -> None:
    abs_path = resolve_source_path(projects_dir, req.project, req.file_field)
    logging.info(
        f"Processing file: {abs_path or '[NOT FOUND]'}, Caller: {req.caller}, Callee: {req.callee}"
    )

    if not abs_path or not is_regular_file(abs_path):
        logging.error(f"File not found (after resolution attempts): {req.project} :: {req.file_field}")
        df.at[req.idx, "PC"] = "FILE_NOT_FOUND"
        return

    # Load source (cached)
    if abs_path not in source_cache:
        try:
            analyzer = SourceCodeAnalyzer(abs_path)
        except IsADirectoryError:
            logging.error(f"Path is a directory (skipping): {abs_path}")
            df.at[req.idx, "PC"] = "FILE_NOT_FOUND"
            return
        source_cache[abs_path] = analyzer.source_code

    pcs = _get_cached_pcs(abs_path, req.caller, req.callee, source_cache, extractor_cache, pc_cache)

    # First PC in the original row
    df.at[req.idx, "PC"] = pcs[0]

    # Remaining PCs become additional rows
    for pc in pcs[1:]:
        new_row = df.loc[req.idx].copy()
        new_row["PC"] = pc
        extra_rows.append(new_row)


def run_extraction_pipeline(df: pd.DataFrame, projects_dir: str) -> pd.DataFrame:
    """
    Execute the batch PC extraction over a normalized input DataFrame.

    Expected input columns:
      Project, File, Caller, Callee

    Returns:
      A new DataFrame with a populated `PC` column, preserving the current
      status/error semantics and multi-call expansion behavior.
    """
    _validate_input_df(df)
    df = _prepare_input_df(df)

    # Cache loaded source code per absolute file path (big speedup in large datasets)
    source_cache: Dict[str, str] = {}

    # Cache parsed extractors per absolute file path (avoids rebuilding indices/PC maps)
    extractor_cache: Dict[str, PresenceConditionExtractor] = {}

    # Cache extraction results per (abs_path, caller, callee)
    pc_cache: Dict[Tuple[str, str, str], List[str]] = {}

    # Collect extra rows when a caller contains multiple call sites for the same callee
    extra_rows: List[pd.Series] = []

    for req in _iter_requests(df):
        _process_request(req, df, projects_dir, source_cache, extractor_cache, pc_cache, extra_rows)

    return _finalize_output_df(df, extra_rows)
