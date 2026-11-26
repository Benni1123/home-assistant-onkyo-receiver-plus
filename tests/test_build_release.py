"""Exercise both archive layouts and the release-tag guard."""

from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.build_release import ASSETS, COMPONENT, DOMAIN, ROOT, build


class BuildReleaseTest(unittest.TestCase):
    def test_home_assistant_and_hacs_zip_layouts(self):
        manifest = json.loads((ROOT / COMPONENT / "manifest.json").read_bytes())
        with TemporaryDirectory() as directory:
            manual, hacs, checksums = build(Path(directory), f"v{manifest['version']}")
            for zip_path, prefix in (
                (manual, COMPONENT.as_posix() + "/"),
                (hacs, ""),
            ):
                with ZipFile(zip_path) as archive:
                    self.assertEqual(json.loads(archive.read(prefix + "manifest.json"))["domain"], DOMAIN)
                    self.assertTrue({prefix + name for name in ASSETS} <= set(archive.namelist()))
                    self.assertIn(prefix + "LICENSE", archive.namelist())
                    self.assertNotIn("tests/test_media_player.py", archive.namelist())
                digest = sha256(zip_path.read_bytes()).hexdigest()
                self.assertIn(f"{digest}  {zip_path.name}", checksums.read_text())

    def test_reject_tag_that_does_not_match_manifest(self):
        with TemporaryDirectory() as directory, self.assertRaisesRegex(ValueError, "does not match"):
            build(Path(directory), "v0.0.0")
