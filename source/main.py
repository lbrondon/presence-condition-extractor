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
from typing import Tuple

from CSVHandler import CSVHandler
from extraction_pipeline import run_extraction_pipeline
from logging_config import configure_logging
from streaming_extraction import stream_extraction_to_csv

configure_logging()


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
    input_csv_root = os.path.join(root, "57_cs_projects.csv")
    input_csv_source = os.path.join(root, "source", "57_cs_projects.csv")
    input_csv = input_csv_root if os.path.exists(input_csv_root) else input_csv_source

    return input_csv, projects_dir, output_dir


def main() -> None:
    input_csv_default, projects_dir_default, output_dir_default = _default_paths()

    parser = argparse.ArgumentParser(description="Extract presence conditions for caller→callee pairs.")
    parser.add_argument("--input", default=input_csv_default, help="Input CSV with Project,File,Caller,Callee.")
    parser.add_argument("--projects", default=projects_dir_default, help="Directory containing all projects.")
    parser.add_argument("--output", default=os.path.join(output_dir_default, "57_cs_projects_with_pc.csv"),
                        help="Output CSV path.")
    parser.add_argument(
        "--execution-mode",
        choices=("stream", "in-memory"),
        default="stream",
        help="Use streaming mode to reduce peak memory (default) or in-memory mode.",
    )
    parser.add_argument(
        "--ingest-chunk-size",
        type=int,
        default=100_000,
        help="Rows per CSV chunk while reading input in streaming mode.",
    )
    parser.add_argument(
        "--process-batch-size",
        type=int,
        default=50_000,
        help="Rows per processing batch after optional on-disk deduplication.",
    )
    parser.add_argument(
        "--progress-every",
        type=int,
        default=10_000,
        help="Log progress every N requests within each batch (0 disables).",
    )
    parser.add_argument(
        "--disable-request-dedup",
        action="store_true",
        help="Disable on-disk deduplication of (Project, File, Caller, Callee) requests in streaming mode.",
    )
    args = parser.parse_args()

    input_csv_path = args.input
    projects_dir = args.projects
    output_csv_path = args.output

    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    logging.info(f"Input CSV: {input_csv_path}")
    logging.info(f"Projects dir: {projects_dir}")
    logging.info(f"Output CSV: {output_csv_path}")

    if args.execution_mode == "in-memory":
        csv_handler = CSVHandler(input_csv_path)
        df = csv_handler.load_csv()
        df = run_extraction_pipeline(df, projects_dir, progress_every=args.progress_every)
        csv_handler.dataframe = df
        csv_handler.save_csv(output_csv_path)
    else:
        stream_extraction_to_csv(
            input_csv_path=input_csv_path,
            output_csv_path=output_csv_path,
            projects_dir=projects_dir,
            ingest_chunk_size=args.ingest_chunk_size,
            process_batch_size=args.process_batch_size,
            progress_every=args.progress_every,
            deduplicate_requests=not args.disable_request_dedup,
        )

    logging.info("Extraction completed successfully.")


if __name__ == "__main__":
    main()
