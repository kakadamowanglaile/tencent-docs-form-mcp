"""本机傻瓜式 Open API 设置窗口测试。"""

from __future__ import annotations

import re
import urllib.error
import urllib.parse
import urllib.request
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openapi_setup_ui import (
    SetupUIState,
    _page,
    open_setup_ui,
    stop_setup_ui,
)


class SetupUIPageTests(unittest.TestCase):
    def tearDown(self) -> None:
        stop_setup_ui()

    def test_existing_profile_page_never_renders_secrets(self) -> None:
        profile = SimpleNamespace(
            app_configured=True,
            authorized=False,
            client_id="client-12345678",
            client_secret="private-secret",
            access_token="access-secret",
            refresh_token="refresh-secret",
        )
        with patch("openapi_setup_ui._safe_profile", return_value=profile):
            rendered = _page(SetupUIState("csrf-value"))

        self.assertIn("授权腾讯文档", rendered)
        self.assertIn("clie••••5678", rendered)
        self.assertNotIn("private-secret", rendered)
        self.assertNotIn("access-secret", rendered)
        self.assertNotIn("refresh-secret", rendered)

    def test_local_server_rejects_bad_host(self) -> None:
        opened: list[str] = []
        with patch("openapi_setup_ui._safe_profile", return_value=None):
            result = open_setup_ui(browser_opener=lambda url: opened.append(url))
        self.assertTrue(result["setup_ui_opened"])

        request = urllib.request.Request(opened[0], headers={"Host": "evil.example"})
        with self.assertRaises(urllib.error.HTTPError) as raised:
            urllib.request.urlopen(request, timeout=2)
        self.assertEqual(raised.exception.code, 403)

    def test_first_time_form_saves_locally_and_starts_authorization(self) -> None:
        opened: list[str] = []
        with patch("openapi_setup_ui._safe_profile", return_value=None):
            open_setup_ui(browser_opener=lambda url: opened.append(url))
            with urllib.request.urlopen(opened[0], timeout=2) as response:
                page = response.read().decode("utf-8")
        csrf = re.search(r'name="csrf_token" value="([^"]+)"', page)
        self.assertIsNotNone(csrf)
        form = urllib.parse.urlencode(
            {
                "csrf_token": csrf.group(1),
                "client_id": "client",
                "client_secret": "private-secret",
                "redirect_uri": "https://example.com/callback",
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            urllib.parse.urljoin(opened[0], "/configure"),
            data=form,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with patch("openapi_setup_ui.configure_openapi_app") as configure, patch(
            "openapi_setup_ui._start_authorization"
        ) as start_authorization, patch(
            "openapi_setup_ui._safe_profile", return_value=None
        ):
            with urllib.request.urlopen(request, timeout=2) as response:
                response.read()

        configure.assert_called_once_with(
            "client", "private-secret", "https://example.com/callback"
        )
        start_authorization.assert_called_once()


if __name__ == "__main__":
    unittest.main()
