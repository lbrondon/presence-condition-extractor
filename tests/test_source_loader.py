import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from source_loader import load_source_code  # noqa: E402


class SourceLoaderTests(unittest.TestCase):
    def test_loads_utf8_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit.c"
            path.write_text("int main(void) { return 0; }\n", encoding="utf-8")
            self.assertIn("main", load_source_code(str(path)))

    def test_preserves_encoding_fallback_behavior(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "unit.c"
            path.write_bytes("/* USART’s DMA interface */\n".encode("cp1252"))
            self.assertIn("USART", load_source_code(str(path)))

    def test_raises_is_a_directory_for_directory_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IsADirectoryError):
                load_source_code(tmp)


if __name__ == "__main__":
    unittest.main()
