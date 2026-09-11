"""验证腾讯文档正式 Open API 的请求映射与凭据安全。"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from openapi_client import (
    ACCESS_TOKEN_ENV,
    CLIENT_ID_ENV,
    CLIENT_SECRET_ENV,
    OPEN_ID_ENV,
    REFRESH_TOKEN_ENV,
    OpenAPICredentials,
    TencentDocsOpenAPIClient,
    load_openapi_credentials,
)
from tencent_form import TencentDocsError


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self.payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self.payload


class Recorder:
    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.calls: list[tuple[str, str, dict]] = []
        self.responses = responses or [FakeResponse({"ret": 0, "msg": "Succeed"})]

    async def __call__(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class OpenAPICredentialTests(unittest.TestCase):
    def test_requires_complete_call_or_refresh_credentials(self) -> None:
        with patch.dict(os.environ, {}, clear=True), patch(
            "openapi_auth.load_openapi_profile", return_value=None
        ):
            self.assertIsNone(load_openapi_credentials(required=False))
            with self.assertRaises(TencentDocsError):
                load_openapi_credentials(required=True)

    def test_status_never_returns_secret_values(self) -> None:
        credentials = OpenAPICredentials(
            client_id="client",
            open_id="user",
            access_token="access-secret",
            client_secret="client-secret",
            refresh_token="refresh-secret",
        )
        with patch("openapi_auth.load_openapi_profile", return_value=None):
            status = TencentDocsOpenAPIClient(credentials).configuration_status()

        rendered = repr(status)
        self.assertTrue(status["configured"])
        self.assertTrue(status["automatic_refresh_configured"])
        self.assertNotIn("access-secret", rendered)
        self.assertNotIn("client-secret", rendered)
        self.assertNotIn("refresh-secret", rendered)
        self.assertNotIn("user", rendered)

    def test_loads_credentials_saved_in_system_keyring(self) -> None:
        saved = SimpleNamespace(
            client_id="saved-client",
            client_secret="saved-secret",
            open_id="saved-user",
            access_token="saved-access",
            refresh_token="saved-refresh",
        )
        with patch.dict(os.environ, {}, clear=True), patch(
            "openapi_auth.load_openapi_profile", return_value=saved
        ):
            credentials = load_openapi_credentials(required=True)

        self.assertIsNotNone(credentials)
        assert credentials is not None
        self.assertTrue(credentials.can_call)
        self.assertTrue(credentials.can_refresh)
        self.assertEqual(credentials.client_id, "saved-client")

    def test_status_distinguishes_app_configuration_from_user_authorization(self) -> None:
        profile = SimpleNamespace(
            app_configured=True,
            client_id="saved-client",
            client_secret="saved-secret",
            open_id="",
            access_token="",
            refresh_token="",
        )
        with patch.dict(os.environ, {}, clear=True), patch(
            "openapi_auth.load_openapi_profile", return_value=profile
        ):
            status = TencentDocsOpenAPIClient().configuration_status()

        self.assertFalse(status["configured"])
        self.assertTrue(status["app_configured"])
        self.assertFalse(status["authorized"])


class OpenAPIRequestTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.credentials = OpenAPICredentials("client", "user", "access")
        self.recorder = Recorder()
        self.client = TencentDocsOpenAPIClient(
            self.credentials, requester=self.recorder
        )

    async def test_adds_official_headers_without_returning_them(self) -> None:
        result = await self.client.set_starred("file", True)

        method, url, kwargs = self.recorder.calls[0]
        self.assertEqual(method, "PATCH")
        self.assertTrue(url.endswith("/openapi/drive/v2/files/file/star"))
        self.assertEqual(kwargs["data"], {"star": 1})
        self.assertEqual(kwargs["headers"]["Client-Id"], "client")
        self.assertEqual(kwargs["headers"]["Open-Id"], "user")
        self.assertEqual(kwargs["headers"]["Access-Token"], "access")
        self.assertEqual(result, {"ret": 0, "msg": "Succeed"})

    async def test_maps_every_missing_public_endpoint(self) -> None:
        calls = [
            (self.client.set_pinned("f", True, "/"), "PATCH", "/files/f/pin"),
            (
                self.client.set_watermark(
                    "f",
                    text="内部",
                    visitor_mark=True,
                    margin="tight",
                    hide_from_owner=True,
                ),
                "PATCH",
                "/files/f/watermark",
            ),
            (self.client.create_shortcut("f", "/"), "POST", "/files/f/shortcut"),
            (self.client.recover_file("f"), "PATCH", "/files/f/recover"),
            (self.client.get_user_access("f"), "GET", "/files/f/access"),
            (
                self.client.get_file_permission("f"),
                "GET",
                "/files/f/permission",
            ),
            (
                self.client.get_folder_permission("folder"),
                "GET",
                "/folders/folder/permission",
            ),
            (
                self.client.transfer_ownership("f", "new-user"),
                "PATCH",
                "/files/f/ownership",
            ),
            (
                self.client.set_file_permission(
                    "f",
                    policy="members",
                    copy_enabled=False,
                    reader_comment_enabled=False,
                ),
                "PATCH",
                "/files/f/permission",
            ),
            (
                self.client.apply_file_permission("f", "write", "需要编辑"),
                "POST",
                "/files/f/permission/apply",
            ),
            (
                self.client.add_collaborators(
                    "f", [{"type": "user", "role": "reader", "id": "u"}]
                ),
                "PATCH",
                "/files/f/collaborators",
            ),
            (
                self.client.remove_collaborator("f", "u"),
                "DELETE",
                "/files/f/collaborators",
            ),
            (
                self.client.list_collaborators("f"),
                "GET",
                "/files/f/collaborators",
            ),
            (
                self.client.filter_files(
                    list_type="folder",
                    sort_type="browse",
                    ascending=False,
                    folder_id="/",
                    start=0,
                    limit=20,
                    owned_only=False,
                    file_types="",
                ),
                "GET",
                "/openapi/drive/v2/filter",
            ),
            (
                self.client.convert_file_id(2, "encoded"),
                "GET",
                "/openapi/drive/v2/util/converter",
            ),
            (self.client.get_usage(), "GET", "/openapi/drive/v2/util/resource-use"),
            (
                self.client.get_unread_count(),
                "GET",
                "/openapi/drive/v2/notification/unread-count",
            ),
            (
                self.client.set_form_release("form", 0),
                "PUT",
                "/openapi/drive/v2/forms/form/release",
            ),
            (
                self.client.generate_form_result("form"),
                "POST",
                "/openapi/drive/v2/forms/form/result",
            ),
            (
                self.client.batch_insert_sheet_images(
                    "book",
                    "sheet",
                    [{"type": 1, "url": "image", "width": 10, "height": 10, "row": 1, "col": 1}],
                ),
                "POST",
                "/openapi/sheetbook/v2/book:batchUpdate",
            ),
        ]

        for awaitable, expected_method, expected_suffix in calls:
            with self.subTest(path=expected_suffix):
                before = len(self.recorder.calls)
                await awaitable
                method, url, _kwargs = self.recorder.calls[before]
                self.assertEqual(method, expected_method)
                self.assertTrue(url.endswith(expected_suffix), url)

    async def test_refreshes_once_after_expired_token(self) -> None:
        recorder = Recorder(
            [
                FakeResponse({"ret": 37019, "msg": "expired"}),
                FakeResponse({"access_token": "new-access", "user_id": "new-user"}),
                FakeResponse({"ret": 0, "msg": "Succeed"}),
            ]
        )
        client = TencentDocsOpenAPIClient(
            OpenAPICredentials(
                client_id="client",
                open_id="old-user",
                access_token="old-access",
                client_secret="secret",
                refresh_token="refresh",
            ),
            requester=recorder,
        )

        with patch("openapi_auth.update_saved_openapi_tokens", return_value=False):
            await client.get_usage()

        self.assertEqual(len(recorder.calls), 3)
        self.assertTrue(recorder.calls[1][1].endswith("/oauth/v2/token"))
        self.assertEqual(recorder.calls[2][2]["headers"]["Access-Token"], "new-access")
        self.assertEqual(recorder.calls[2][2]["headers"]["Open-Id"], "new-user")

    async def test_rejects_empty_permission_update(self) -> None:
        with self.assertRaises(TencentDocsError):
            await self.client.set_file_permission(
                "f", policy=None, copy_enabled=None, reader_comment_enabled=None
            )

    async def test_escapes_external_id_as_one_path_segment(self) -> None:
        await self.client.get_user_access("folder/file")

        _method, url, _kwargs = self.recorder.calls[0]
        self.assertTrue(url.endswith("/files/folder%2Ffile/access"), url)
