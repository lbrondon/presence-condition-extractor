import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "source"
if str(SOURCE_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIR))

from path_resolver import resolve_source_path  # noqa: E402


class PathResolverTests(unittest.TestCase):
    def test_resolves_typical_project_relative_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            target = projects_dir / "proj" / "src" / "unit.c"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("int x;\n", encoding="utf-8")

            resolved = resolve_source_path(str(projects_dir), "proj", "src/unit.c")
            self.assertEqual(Path(resolved), target)

    def test_resolves_when_file_field_already_contains_project_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            target = projects_dir / "proj" / "src" / "unit.c"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("int x;\n", encoding="utf-8")

            resolved = resolve_source_path(str(projects_dir), "proj", "proj/src/unit.c")
            self.assertEqual(Path(resolved), target)

    def test_uses_suffix_fallback_within_project_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            projects_dir = Path(tmp)
            project_root = projects_dir / "proj"
            wrong = project_root / "legacy" / "unit.c"
            right = project_root / "src" / "driver" / "unit.c"
            wrong.parent.mkdir(parents=True, exist_ok=True)
            right.parent.mkdir(parents=True, exist_ok=True)
            wrong.write_text("int old;\n", encoding="utf-8")
            right.write_text("int current;\n", encoding="utf-8")

            resolved = resolve_source_path(str(projects_dir), "proj", "src/driver/unit.c")
            self.assertEqual(Path(resolved), right)

    def test_returns_empty_for_missing_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            resolved = resolve_source_path(tmp, "proj", "missing.c")
            self.assertEqual(resolved, "")


if __name__ == "__main__":
    unittest.main()
