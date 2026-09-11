"""Windows 浏览器登录助手测试。"""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from browser_login import cookie_header_for_docs, find_browser


class BrowserLoginTests(unittest.TestCase):
    def test_cookie_filter_only_keeps_qq_domains(self) -> None:
        result = cookie_header_for_docs(
            [
                {"domain": ".docs.qq.com", "name": "TOK", "value": "token"},
                {"domain": ".qq.com", "name": "uid", "value": "user"},
                {"domain": ".example.com", "name": "secret", "value": "no"},
            ]
        )
        self.assertIn("TOK=token", result)
        self.assertIn("uid=user", result)
        self.assertNotIn("secret", result)

    def test_auto_falls_back_to_edge_when_chrome_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            edge = Path(directory) / "msedge.exe"
            edge.touch()

            def candidates(name: str) -> list[Path]:
                return [edge] if name == "edge" else []

            with patch("browser_login.browser_candidates", side_effect=candidates):
                name, executable = find_browser("auto")

        self.assertEqual(name, "edge")
        self.assertEqual(executable, edge.resolve())


if __name__ == "__main__":
    unittest.main()
