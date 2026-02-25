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

    def test_expands_if_elif_else_with_cpp_exact_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text(
                "void callee(void) {}\n"
                "int caller(void) {\n"
                "#if defined(FOO)\n"
                "  callee();\n"
                "#elif defined(BAR)\n"
                "  callee();\n"
                "#else\n"
                "  callee();\n"
                "#endif\n"
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            out = self._run_single(projects_dir, "proj", "unit.c", "caller", "callee")
            pcs = sorted(out["PC"].tolist())
            self.assertEqual(sorted(["FOO", "!(FOO) && BAR", "!(FOO) && !(BAR)"]), pcs)

    def test_conjoins_nested_preprocessor_conditions(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text(
                "void callee(void) {}\n"
                "int caller(void) {\n"
                "#if OUTER\n"
                "#if defined(INNER)\n"
                "  callee();\n"
                "#endif\n"
                "#endif\n"
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            out = self._run_single(projects_dir, "proj", "unit.c", "caller", "callee")
            self.assertEqual(out.iloc[0]["PC"], "OUTER && INNER")

    def test_deduplicates_multiple_calls_on_same_line_with_same_pc(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            proj_dir = projects_dir / "proj"
            proj_dir.mkdir(parents=True, exist_ok=True)
            (proj_dir / "unit.c").write_text(
                "void callee(void) {}\n"
                "int caller(void) {\n"
                "  callee(); callee();\n"
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            out = self._run_single(projects_dir, "proj", "unit.c", "caller", "callee")
            # The extractor sees both call sites, but the pipeline's final dedup step
            # collapses identical (Project, File, Caller, Callee, PC) rows.
            self.assertEqual(len(out), 1)
            self.assertEqual(out.iloc[0]["PC"], "TRUE")

    def test_pipeline_output_matches_expected_records_for_mixed_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
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
                "  return 0;\n"
                "}\n",
                encoding="utf-8",
            )

            df = pd.DataFrame(
                [
                    {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "callee"},
                    {"Project": "proj", "File": "unit.c", "Caller": "missing", "Callee": "callee"},
                    {"Project": "proj", "File": "missing.c", "Caller": "caller", "Callee": "callee"},
                    {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "defined"},
                ]
            )

            out = run_extraction_pipeline(df, str(projects_dir))
            records = out[["Project", "File", "Caller", "Callee", "PC"]].to_dict(orient="records")

            expected = [
                {"Project": "proj", "File": "unit.c", "Caller": "caller", "Callee": "callee", "PC": "FOO"},
                {
                    "Project": "proj",
                    "File": "unit.c",
                    "Caller": "missing",
                    "Callee": "callee",
                    "PC": "CALLER_NOT_FOUND",
                },
                {
                    "Project": "proj",
                    "File": "missing.c",
                    "Caller": "caller",
                    "Callee": "callee",
                    "PC": "FILE_NOT_FOUND",
                },
                {
                    "Project": "proj",
                    "File": "unit.c",
                    "Caller": "caller",
                    "Callee": "callee",
                    "PC": "!(FOO)",
                },
            ]
            self.assertEqual(records, expected)


if __name__ == "__main__":
    unittest.main()
