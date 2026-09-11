"""面向 WorkBuddy CLI 连接器的集成测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def run_cli(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    command_env = os.environ.copy()
    command_env.update(env or {})
    return subprocess.run(
        [sys.executable, "-m", "tencent_docs_cli", *args],
        cwd=ROOT,
        env=command_env,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )


class TencentDocsCliTests(unittest.TestCase):
    def test_structured_result_is_unwrapped(self) -> None:
        from tencent_docs_cli import _business_result

        result = SimpleNamespace(
            is_error=False,
            structured_content={"result": {"title": "测试收集表"}},
            content=[],
        )

        self.assertEqual(_business_result(result), {"title": "测试收集表"})

    def test_mcp_console_entry_has_callable_main(self) -> None:
        import gateway

        self.assertTrue(callable(gateway.main))

    def test_tools_json_exposes_all_extension_tools(self) -> None:
        result = run_cli("tools", "--json")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        names = {tool["name"] for tool in payload["tools"]}
        self.assertEqual(payload["count"], 38)
        self.assertIn("tencent_docs_inspect_form", names)
        self.assertIn("tencent_docs_openapi_batch_insert_sheet_images", names)

    def test_call_returns_business_json_without_mcp_envelope(self) -> None:
        result = run_cli(
            "call",
            "tencent_docs_openapi_status",
            "--json",
            '{"validate": false}',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload["configured"])
        self.assertNotIn("content", payload)

    def test_call_rejects_invalid_json(self) -> None:
        result = run_cli("call", "tencent_docs_openapi_status", "--json", "{")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("参数 JSON 无效", result.stderr)

    def test_logout_marker_blocks_browser_session_until_next_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            env = {"TENCENT_DOCS_CONNECTOR_STATE_DIR": temp_dir}
            logged_out = run_cli("auth", "logout", env=env)
            status = run_cli("auth", "status", env=env)
            login = run_cli("auth", "login", env=env)

        self.assertEqual(logged_out.returncode, 0, logged_out.stderr)
        self.assertNotEqual(status.returncode, 0)
        self.assertIn("Logged out", status.stdout)
        self.assertEqual(login.returncode, 0, login.stderr)
        self.assertIn("https://docs.qq.com/", login.stdout)


if __name__ == "__main__":
    unittest.main()
