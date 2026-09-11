"""用户自有应用的 OAuth2 授权流程测试。"""

from __future__ import annotations

import base64
import json
import urllib.parse
import urllib.request
import unittest
from pathlib import Path
from unittest.mock import patch

from openapi_auth import (
    CALLBACK_PORTS,
    DEFAULT_REDIRECT_URI,
    KEYRING_ACCESS_TOKEN_ACCOUNT,
    KEYRING_CLIENT_SECRET_ACCOUNT,
    KEYRING_METADATA_ACCOUNT,
    KEYRING_REFRESH_TOKEN_ACCOUNT,
    OpenAPIProfile,
    authorize_interactively,
    build_authorization_url,
    configure_openapi_app,
    load_openapi_profile,
    save_openapi_profile,
)
from tencent_form import TencentDocsError


class OAuthProfileTests(unittest.TestCase):
    def test_keyring_stores_large_secrets_in_separate_entries(self) -> None:
        class FakeKeyring:
            def __init__(self) -> None:
                self.values: dict[tuple[str, str], str] = {}

            def set_password(self, service: str, account: str, value: str) -> None:
                self.values[(service, account)] = value

            def get_password(self, service: str, account: str) -> str | None:
                return self.values.get((service, account))

            def delete_password(self, service: str, account: str) -> None:
                self.values.pop((service, account), None)

        fake = FakeKeyring()
        profile = OpenAPIProfile(
            "client",
            "private-secret",
            DEFAULT_REDIRECT_URI,
            "open-id",
            "access-secret",
            "refresh-secret",
            123,
        )
        with patch("openapi_auth._keyring_module", return_value=(fake, Exception)):
            save_openapi_profile(profile)
            loaded = load_openapi_profile(required=True)

        metadata = next(
            value
            for (_service, account), value in fake.values.items()
            if account == KEYRING_METADATA_ACCOUNT
        )
        self.assertNotIn("private-secret", metadata)
        self.assertNotIn("access-secret", metadata)
        self.assertNotIn("refresh-secret", metadata)
        self.assertEqual(
            {
                KEYRING_METADATA_ACCOUNT,
                KEYRING_CLIENT_SECRET_ACCOUNT,
                KEYRING_ACCESS_TOKEN_ACCOUNT,
                KEYRING_REFRESH_TOKEN_ACCOUNT,
            },
            {account for _service, account in fake.values},
        )
        self.assertEqual(loaded, profile)

    def test_rejects_non_https_redirect_uri(self) -> None:
        with patch("openapi_auth.load_openapi_profile", return_value=None), patch(
            "openapi_auth.save_openapi_profile"
        ):
            with self.assertRaises(TencentDocsError):
                configure_openapi_app("client", "secret", "http://localhost/callback")

    def test_authorization_url_contains_public_values_but_not_secret(self) -> None:
        profile = OpenAPIProfile("client", "private-secret", DEFAULT_REDIRECT_URI)
        url = build_authorization_url(profile, "state-value")
        parsed = urllib.parse.urlparse(url)
        query = urllib.parse.parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(query["client_id"], ["client"])
        self.assertEqual(query["redirect_uri"], [DEFAULT_REDIRECT_URI])
        self.assertEqual(query["scope"], ["all"])
        self.assertNotIn("private-secret", url)


class InteractiveOAuthTests(unittest.TestCase):
    def test_browser_callback_exchanges_and_saves_tokens(self) -> None:
        profile = OpenAPIProfile("client", "secret", DEFAULT_REDIRECT_URI)
        saved: list[OpenAPIProfile] = []

        def open_browser(url: str) -> bool:
            state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
            padded = state + "=" * ((4 - len(state) % 4) % 4)
            relay = json.loads(base64.urlsafe_b64decode(padded))
            callback = "http://127.0.0.1:{}/oauth/callback?{}".format(
                relay["port"],
                urllib.parse.urlencode({"code": "one-time-code", "state": state}),
            )
            with urllib.request.urlopen(callback, timeout=2) as response:
                self.assertEqual(response.status, 200)
            return True

        def exchange(_url: str) -> dict:
            return {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "user_id": "open-id-secret",
                "expires_in": 2592000,
            }

        with patch("openapi_auth.load_openapi_profile", return_value=profile), patch(
            "openapi_auth.save_openapi_profile", side_effect=saved.append
        ):
            result = authorize_interactively(
                10,
                browser_opener=open_browser,
                token_requester=exchange,
            )

        self.assertTrue(result["authorized"])
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].access_token, "access-secret")
        rendered = repr(result)
        self.assertNotIn("access-secret", rendered)
        self.assertNotIn("refresh-secret", rendered)
        self.assertNotIn("open-id-secret", rendered)

    def test_static_relay_only_targets_loopback(self) -> None:
        script = (
            Path(__file__).resolve().parents[1] / "oauth-callback" / "callback.js"
        ).read_text(encoding="utf-8")
        self.assertIn("http://127.0.0.1:", script)
        self.assertIn("port < 49680", script)
        self.assertIn("port > 49689", script)
        self.assertNotIn("client_secret", script)
        self.assertNotIn("access_token", script)

    def test_callback_ports_are_dedicated_high_ports(self) -> None:
        self.assertEqual(CALLBACK_PORTS, tuple(range(49680, 49690)))


if __name__ == "__main__":
    unittest.main()
