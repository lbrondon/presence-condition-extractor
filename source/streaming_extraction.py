from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
from typing import Iterable

import pandas as pd

from extraction_pipeline import run_extraction_pipeline
from pipeline_services import PipelineServices

REQUIRED_COLUMNS = ("Project", "File", "Caller", "Callee")
OUTPUT_COLUMNS = ["Project", "File", "Caller", "Callee", "PC"]


def _validate_columns(columns: Iterable[str]) -> None:
    missing = [col for col in REQUIRED_COLUMNS if col not in columns]
    if missing:
        raise KeyError(f"Missing required column in CSV: {missing}")


def _normalize_request_chunk(chunk: pd.DataFrame) -> pd.DataFrame:
    normalized = chunk.loc[:, REQUIRED_COLUMNS].copy()
    for col in REQUIRED_COLUMNS:
        normalized[col] = normalized[col].astype(str).str.strip()
    return normalized


def _configure_sqlite_connection(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode = OFF;")
    conn.execute("PRAGMA synchronous = OFF;")
    conn.execute("PRAGMA temp_store = MEMORY;")


def _create_requests_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS requests (
            seq INTEGER PRIMARY KEY AUTOINCREMENT,
            project TEXT NOT NULL,
            file_field TEXT NOT NULL,
            caller TEXT NOT NULL,
            callee TEXT NOT NULL,
            UNIQUE(project, file_field, caller, callee)
        );
        """
    )


def _ingest_unique_requests(
    input_csv_path: str,
    conn: sqlite3.Connection,
    chunk_size: int,
) -> tuple[int, int]:
    total_rows = 0
    unique_rows = 0

    for chunk_idx, chunk in enumerate(pd.read_csv(input_csv_path, chunksize=chunk_size), start=1):
        _validate_columns(chunk.columns)
        normalized = _normalize_request_chunk(chunk)

        rows = list(normalized.itertuples(index=False, name=None))
        total_rows += len(rows)

        before = conn.total_changes
        conn.executemany(
            """
            INSERT OR IGNORE INTO requests(project, file_field, caller, callee)
            VALUES (?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        unique_rows += conn.total_changes - before

        logging.info(
            "Ingested chunk %d: %d rows (%d unique so far).",
            chunk_idx,
            len(rows),
            unique_rows,
        )

    return total_rows, unique_rows


def _iter_unique_request_batches(conn: sqlite3.Connection, batch_size: int):
    cursor = conn.execute(
        """
        SELECT project, file_field, caller, callee
        FROM requests
        ORDER BY seq
        """
    )

    while True:
        rows = cursor.fetchmany(batch_size)
        if not rows:
            break
        yield pd.DataFrame(rows, columns=REQUIRED_COLUMNS)


def _write_empty_output(output_csv_path: str) -> None:
    pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(output_csv_path, index=False)


def stream_extraction_to_csv(
    input_csv_path: str,
    output_csv_path: str,
    projects_dir: str,
    services: PipelineServices | None = None,
    ingest_chunk_size: int = 100_000,
    process_batch_size: int = 50_000,
    progress_every: int = 0,
    deduplicate_requests: bool = True,
) -> None:
    """
    Execute PC extraction without loading the whole input CSV into memory.

    This preserves extraction semantics by delegating each batch to
    `run_extraction_pipeline` (same algorithm), while reducing peak memory by:
      - Reading input in chunks.
      - Optionally deduplicating requests on disk (SQLite).
      - Writing output incrementally.
    """
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    if not deduplicate_requests:
        _run_streaming_without_dedup(
            input_csv_path=input_csv_path,
            output_csv_path=output_csv_path,
            projects_dir=projects_dir,
            services=services,
            ingest_chunk_size=ingest_chunk_size,
            progress_every=progress_every,
        )
        return

    tmp_file = tempfile.NamedTemporaryFile(prefix="pc_requests_", suffix=".sqlite3", delete=False)
    tmp_db_path = tmp_file.name
    tmp_file.close()

    conn: sqlite3.Connection | None = None
    try:
        conn = sqlite3.connect(tmp_db_path)
        _configure_sqlite_connection(conn)
        _create_requests_table(conn)

        total_rows, unique_rows = _ingest_unique_requests(input_csv_path, conn, ingest_chunk_size)
        logging.info(
            "Finished ingest: %d total rows, %d unique requests (dedup ratio %.2f%%).",
            total_rows,
            unique_rows,
            100.0 * (1.0 - (unique_rows / total_rows if total_rows else 1.0)),
        )

        wrote_output = False
        for batch_idx, request_batch in enumerate(
            _iter_unique_request_batches(conn, process_batch_size),
            start=1,
        ):
            out_df = run_extraction_pipeline(
                request_batch,
                projects_dir,
                services=services,
                progress_every=progress_every,
            )

            if out_df.empty:
                continue

            out_df.to_csv(
                output_csv_path,
                mode="a" if wrote_output else "w",
                header=not wrote_output,
                index=False,
            )
            wrote_output = True

            logging.info(
                "Processed output batch %d: %d request rows -> %d output rows.",
                batch_idx,
                len(request_batch),
                len(out_df),
            )

        if not wrote_output:
            _write_empty_output(output_csv_path)

    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass
        try:
            os.unlink(tmp_db_path)
        except FileNotFoundError:
            pass


def _run_streaming_without_dedup(
    input_csv_path: str,
    output_csv_path: str,
    projects_dir: str,
    services: PipelineServices | None,
    ingest_chunk_size: int,
    progress_every: int,
) -> None:
    wrote_output = False

    for chunk_idx, chunk in enumerate(pd.read_csv(input_csv_path, chunksize=ingest_chunk_size), start=1):
        _validate_columns(chunk.columns)
        normalized = _normalize_request_chunk(chunk)

        out_df = run_extraction_pipeline(
            normalized,
            projects_dir,
            services=services,
            progress_every=progress_every,
        )

        if out_df.empty:
            continue

        out_df.to_csv(
            output_csv_path,
            mode="a" if wrote_output else "w",
            header=not wrote_output,
            index=False,
        )
        wrote_output = True

        logging.info(
            "Processed chunk %d: %d request rows -> %d output rows.",
            chunk_idx,
            len(normalized),
            len(out_df),
        )

    if not wrote_output:
        _write_empty_output(output_csv_path)
