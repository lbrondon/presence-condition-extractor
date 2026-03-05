import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from extraction_pipeline import run_extraction_pipeline  # noqa: E402
from streaming_extraction import stream_extraction_to_csv  # noqa: E402


class StreamingExtractionTests(unittest.TestCase):
    def test_streaming_mode_matches_in_memory_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            projects_dir = tmp_path / "projects"
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)

            (proj_dir / "unit.c").write_text(
                "void callee(void) {}\n"
                "int caller(void) {\n"
                "#if defined(FOO)\n"
                "  callee();\n"
                "#else\n"
                "  callee();\n"
                "#endif\n"
                "  callee(); callee();\n"
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            input_csv = tmp_path / "input.csv"
            output_csv = tmp_path / "out_stream.csv"

            input_df = pd.DataFrame(
                [
                    {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "callee"},
                    {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "callee"},
                    {"Project": "proj", "File": "unit.c", "Caller": "missing", "Callee": "callee"},
                    {"Project": "proj", "File": "missing.c", "Caller": "caller", "Callee": "callee"},
                    {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "defined"},
                ]
            )
            input_df.to_csv(input_csv, index=False)

            expected_df = run_extraction_pipeline(input_df, str(projects_dir))
            expected_df = expected_df.sort_values(
                ["Project", "File", "Caller", "Callee", "PC"]
            ).reset_index(drop=True)

            stream_extraction_to_csv(
                input_csv_path=str(input_csv),
                output_csv_path=str(output_csv),
                projects_dir=str(projects_dir),
                ingest_chunk_size=2,
                process_batch_size=2,
                progress_every=0,
                deduplicate_requests=True,
            )

            streamed_df = pd.read_csv(output_csv)
            streamed_df = streamed_df.sort_values(
                ["Project", "File", "Caller", "Callee", "PC"]
            ).reset_index(drop=True)

            self.assertTrue(expected_df.equals(streamed_df))


if __name__ == "__main__":
    unittest.main()
