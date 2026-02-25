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


class ExtractionPipelineTests(unittest.TestCase):
    def _run_single(self, projects_dir: Path, project: str, file_path: str, caller: str, callee: str):
        df = pd.DataFrame(
            [{"Project": project, "File": file_path, "Caller": caller, "Callee": callee}]
        )
        return run_extraction_pipeline(df, str(projects_dir))

    def test_marks_file_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = self._run_single(Path(tmp), "proj", "missing.c", "caller", "callee")
            self.assertEqual(out.iloc[0]["PC"], "FILE_NOT_FOUND")

    def test_marks_caller_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text("int caller(void) { return 0; }\n", encoding="utf-8")

            out = self._run_single(projects_dir, "proj", "unit.c", "missing_caller", "callee")
            self.assertEqual(out.iloc[0]["PC"], "CALLER_NOT_FOUND")

    def test_marks_call_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text(
                "int caller(void) {\n"
                "    return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            out = self._run_single(projects_dir, "proj", "unit.c", "caller", "callee")
            self.assertEqual(out.iloc[0]["PC"], "CALL_NOT_FOUND")

    def test_returns_true_when_call_is_unconditional(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text(
                "void callee(void) {}\n"
                "int caller(void) {\n"
                "    callee();\n"
                "    return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            out = self._run_single(projects_dir, "proj", "unit.c", "caller", "callee")
            self.assertEqual(out.iloc[0]["PC"], "TRUE")


if __name__ == "__main__":
    unittest.main()
