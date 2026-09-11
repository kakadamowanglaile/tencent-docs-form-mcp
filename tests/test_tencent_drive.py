"""验证官方 MCP 未打包的文件管理扩展。"""

import unittest
from http.cookiejar import CookieJar
from unittest.mock import patch

from tencent_drive import TencentDriveClient
from tencent_form import AuthContext, TencentDocsError


class DriveClientTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TencentDriveClient(AuthContext(CookieJar(), "xsrf", "test"))

    def test_summarizes_file_list_without_account_fields(self) -> None:
        response = {
            "retcode": 0,
            "result": {
                "files": [
                    {
                        "doc_type": 2,
                        "mime_type": "application/vnd.tdocs-apps.form",
                        "entry": {
                            "file_id": "abc",
                            "name": "测试表",
                            "doc_url": "https://docs.qq.com/form/page/abc",
                            "entry_parent_id": "/",
                            "is_starred": True,
                        },
                        "meta": {"owner_nick": "must-not-leak"},
                    }
                ],
                "finish": True,
            },
        }
        with patch.object(self.client, "_request_json", return_value=response):
            result = self.client.list_files("recent", count=10)

        self.assertEqual(result["count"], 1)
        self.assertEqual(result["files"][0]["file_id"], "abc")
        self.assertTrue(result["files"][0]["is_starred"])
        self.assertNotIn("owner_nick", result["files"][0])

    def test_star_uses_form_encoded_internal_endpoint(self) -> None:
        with patch.object(
            self.client, "_request_json", return_value={"retcode": 0, "msg": "ok"}
        ) as request:
            result = self.client.set_starred("abc", True)

        self.assertTrue(result["is_starred"] if "is_starred" in result else result["starred"])
        self.assertEqual(request.call_args.kwargs["form"]["pad_id"], "abc")
        self.assertEqual(request.call_args.kwargs["form"]["is_cancel"], 0)

    def test_permanent_delete_uses_item_specific_endpoint(self) -> None:
        with patch.object(
            self.client, "_request_json", return_value={"retcode": 0, "msg": "ok"}
        ) as request:
            result = self.client.permanently_delete_trash_item("file", "abc", "/")

        self.assertTrue(result["permanently_deleted"])
        self.assertEqual(
            request.call_args.args[0], "/cgi-bin/online_docs/trash_dropdoc"
        )
        self.assertEqual(request.call_args.kwargs["multipart"]["pad_id"], "abc")

    def test_list_versions_reports_unsupported_online_document(self) -> None:
        with patch.object(
            self.client,
            "_request_json",
            return_value={"retcode": 320101, "msg": "unsupported ext"},
        ):
            result = self.client.list_versions("online-form-id")

        self.assertEqual(
            result,
            {
                "file_id": "online-form-id",
                "supported": False,
                "versions": [],
                "reason": "腾讯云盘版本接口不支持该在线文档类型。",
            },
        )

    def test_list_versions_keeps_other_api_errors(self) -> None:
        with patch.object(
            self.client,
            "_request_json",
            return_value={"retcode": 12345, "msg": "permission denied"},
        ):
            with self.assertRaises(TencentDocsError):
                self.client.list_versions("abc")

    def test_list_versions_marks_supported_upload(self) -> None:
        with patch.object(
            self.client,
            "_request_json",
            return_value={"retcode": 0, "result": [{"version": 2}]},
        ):
            result = self.client.list_versions("uploaded-file-id")

        self.assertEqual(
            result,
            {
                "file_id": "uploaded-file-id",
                "supported": True,
                "versions": [{"version": 2}],
            },
        )
