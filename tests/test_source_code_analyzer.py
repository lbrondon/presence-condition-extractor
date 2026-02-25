import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from SourceCodeAnalyzer import SourceCodeAnalyzer  # noqa: E402


class SourceCodeAnalyzerTests(unittest.TestCase):
    def test_loads_utf8_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit.c"
            path.write_text("int main(void) { return 0; }\n", encoding="utf-8")

            analyzer = SourceCodeAnalyzer(str(path))
            self.assertIn("main", analyzer.source_code)

    def test_falls_back_to_cp1252_for_non_utf8_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit.c"
            text = "/* USART’s DMA interface */\nint main(void) { return 0; }\n"
            path.write_bytes(text.encode("cp1252"))

            analyzer = SourceCodeAnalyzer(str(path))
            self.assertIn("USART", analyzer.source_code)
            self.assertIn("main", analyzer.source_code)

    def test_legacy_find_function_definition_is_backward_compatible(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit.c"
            path.write_text(
                "static int helper(void) {\n"
                "  return 1;\n"
                "}\n",
                encoding="utf-8",
            )

            analyzer = SourceCodeAnalyzer(str(path))
            match = analyzer.find_function_definition("helper")
            self.assertIsNotNone(match)


if __name__ == "__main__":
    unittest.main()
