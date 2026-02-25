import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from source_path_service import resolve_existing_source_path  # noqa: E402


class SourcePathServiceTests(unittest.TestCase):
    def test_returns_resolved_existing_regular_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            target = projects_dir / "proj" / "src" / "unit.c"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("int x;\n", encoding="utf-8")

            resolved = resolve_existing_source_path(str(projects_dir), "proj", "src/unit.c")
            self.assertEqual(Path(resolved), target)

    def test_returns_empty_for_missing_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolved = resolve_existing_source_path(tmp, "proj", "missing.c")
            self.assertEqual(resolved, "")

    def test_returns_empty_when_resolved_path_is_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            target_dir = projects_dir / "proj" / "src"
            target_dir.mkdir(parents=True, exist_ok=True)

            resolved = resolve_existing_source_path(str(projects_dir), "proj", "src")
            self.assertEqual(resolved, "")


if __name__ == "__main__":
    unittest.main()
