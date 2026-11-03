"""Verify public distribution contains its license and excludes run artifacts."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publication_engine", ROOT / "scripts/patent_perspectives.py")
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)


class PublicationPackageTests(unittest.TestCase):
    def test_license_and_usage_notice_are_distributed(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skill.zip"
            result = engine.package_skill(destination)
            with zipfile.ZipFile(destination) as archive:
                self.assertIsNone(archive.testzip())
                self.assertEqual(archive.read("patent-perspectives/LICENSE"), (ROOT / "LICENSE").read_bytes())
                self.assertIn("patent-perspectives/README.md", archive.namelist())
                self.assertEqual(result["files"], len(archive.namelist()))

    def test_database_and_cache_are_not_distributed(self):
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "skill.zip"
            engine.package_skill(destination)
            with zipfile.ZipFile(destination) as archive:
                names = archive.namelist()
                self.assertFalse(any("/.runtime/" in name or "/__pycache__/" in name for name in names))
                self.assertFalse(any(Path(name).suffix in (".sqlite", ".db", ".zip") for name in names))


if __name__ == "__main__":
    unittest.main()
