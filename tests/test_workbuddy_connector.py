"""WorkBuddy 上传包的结构和安全检查。"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONNECTOR = ROOT / "workbuddy-connector"


class WorkBuddyConnectorTests(unittest.TestCase):
    def test_connector_metadata_matches_cli_runtime(self) -> None:
        meta = json.loads((CONNECTOR / "connector-meta.json").read_text("utf-8"))
        config = json.loads((CONNECTOR / "cli.json").read_text("utf-8"))

        self.assertEqual(meta["type"], "cli")
        self.assertEqual(meta["minWorkbuddyVersion"], "5.0.0")
        self.assertRegex(meta["source"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
        self.assertEqual(config["runtime"]["type"], "python")
        self.assertIn("darwin", config["init"])
        self.assertIn("linux", config["init"])
        self.assertIn("win32", config["init"])

    def test_connector_contains_icon_and_skill(self) -> None:
        self.assertTrue((CONNECTOR / "icon.svg").is_file())
        skill = CONNECTOR / "skills" / "tencent-docs-extensions" / "SKILL.md"
        self.assertTrue(skill.is_file())
        text = skill.read_text("utf-8")
        self.assertIn("tencent-docs-extension call", text)
        self.assertIn("永久删除", text)

    def test_public_package_files_do_not_contain_credentials(self) -> None:
        forbidden = ("TENCENT_DOCS_COOKIE=", "Client Secret:", "Access-Token:")
        for path in CONNECTOR.rglob("*"):
            if path.is_file():
                text = path.read_text("utf-8")
                for secret in forbidden:
                    self.assertNotIn(secret, text, str(path))

    def test_build_script_creates_uploadable_zip_with_files_at_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "connector.zip"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "build_workbuddy_connector.py"),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            with zipfile.ZipFile(output) as archive:
                names = set(archive.namelist())
        self.assertIn("connector-meta.json", names)
        self.assertIn("cli.json", names)
        self.assertIn("icon.svg", names)
        self.assertIn("skills/tencent-docs-extensions/SKILL.md", names)
        self.assertFalse(any(name.startswith("workbuddy-connector/") for name in names))


if __name__ == "__main__":
    unittest.main()
