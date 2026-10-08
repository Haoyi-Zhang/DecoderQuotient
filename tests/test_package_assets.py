"""The measured fixture is an input asset, not an accidental nested package."""
from pathlib import Path
import shutil
import tempfile
import unittest
import zipfile

from tools.package_check import check_package_assets

ARTIFACT = Path(__file__).resolve().parents[1]


class PackageAssetsTests(unittest.TestCase):
    def fixture(self, root):
        for rel in ("data/measured_context.zip", "results/native-cpu/provenance.json"):
            target = root/"artifact"/rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ARTIFACT/rel, target)

    def test_required_measured_fixture_is_accepted(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            check_package_assets(root)

    def test_unrelated_archive_remains_rejected(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            with zipfile.ZipFile(root/"artifact/extra.zip", "w") as archive:
                archive.writestr("unused.txt", "unused")
            with self.assertRaisesRegex(ValueError, "unexpected nested archive"):
                check_package_assets(root)

    def test_required_fixture_membership_is_checked(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            self.fixture(root)
            with zipfile.ZipFile(root/"artifact/data/measured_context.zip", "w") as archive:
                archive.writestr("wrong.py", "pass")
            with self.assertRaisesRegex(ValueError, "membership"):
                check_package_assets(root)


if __name__ == "__main__":
    unittest.main()
