"""腾讯文档收集表核心逻辑与登录来源测试。"""

import os
import sys
import types
import unittest
from unittest.mock import patch

from tencent_form import (
    TencentDocsError,
    _load_raw_cookie,
    build_form_data,
    compare_spec,
    load_auth,
    parse_form_url,
)


class ParseFormUrlTests(unittest.TestCase):
    def test_accepts_native_form_url(self) -> None:
        address = parse_form_url(
            "https://docs.qq.com/form/page/EXAMPLE_TOKEN?_fid=example-form-id#/edit"
        )
        self.assertEqual(address.token, "EXAMPLE_TOKEN")
        self.assertNotIn("#", address.url)

    def test_rejects_non_tencent_docs_url(self) -> None:
        with self.assertRaises(TencentDocsError):
            parse_form_url("https://example.com/form/page/test")


class BuildFormTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = {
            "title": "测试收集表",
            "subtitle": "功能验证",
            "questions": [
                {"type": "SIMPLE", "title": "反馈", "required": True},
                {
                    "type": "RADIO",
                    "title": "是否正常",
                    "required": True,
                    "options": ["是", "否"],
                },
            ],
        }
        self.server_data = {
            "globalPadId": "300000000$example-form-id",
            "localPadId": "example-form-id",
        }

    def test_builds_questions_and_section_order(self) -> None:
        result = build_form_data(self.spec, self.server_data)
        self.assertEqual(result["title"], "测试收集表")
        self.assertEqual([item["type"] for item in result["questions"]], ["SIMPLE", "RADIO"])
        self.assertEqual(result["sections"][0]["qlist"], [item["id"] for item in result["questions"]])
        self.assertTrue(result["questions"][0]["toggle"]["required"])
        self.assertEqual(result["questions"][1]["qdata"]["options"][0]["title"], "是")

    def test_compare_spec_checks_title_and_question_types(self) -> None:
        summary = {
            "title": "测试收集表",
            "questions": [
                {"title": "反馈", "type": "SIMPLE"},
                {"title": "是否正常", "type": "RADIO"},
            ],
        }
        self.assertTrue(compare_spec(self.spec, summary))


class AuthTests(unittest.TestCase):
    ENV_KEYS = (
        "TENCENT_DOCS_COOKIE",
        "TENCENT_DOCS_USE_BROWSER_COOKIES",
        "TENCENT_DOCS_USE_CHROME_COOKIES",
        "TENCENT_DOCS_BROWSER",
        "TENCENT_DOCS_BROWSER_COOKIE_FILE",
        "TENCENT_DOCS_CHROME_COOKIE_FILE",
    )

    def clean_environment(self) -> dict[str, str]:
        return {key: value for key, value in os.environ.items() if key not in self.ENV_KEYS}

    def test_no_explicit_auth_returns_none(self) -> None:
        with patch.dict(os.environ, self.clean_environment(), clear=True):
            self.assertIsNone(load_auth(required=False))

    def test_raw_cookie_requires_tok(self) -> None:
        with self.assertRaisesRegex(TencentDocsError, "缺少 TOK"):
            _load_raw_cookie("uid=example")

    def test_selects_firefox_when_requested(self) -> None:
        expected = _load_raw_cookie("TOK=example-token")
        fake_module = types.SimpleNamespace(firefox=lambda **kwargs: expected.cookie_jar)
        environment = self.clean_environment()
        environment.update(
            {
                "TENCENT_DOCS_USE_BROWSER_COOKIES": "1",
                "TENCENT_DOCS_BROWSER": "firefox",
            }
        )
        with patch.dict(os.environ, environment, clear=True), patch.dict(
            sys.modules, {"browser_cookie3": fake_module}
        ):
            auth = load_auth(required=True)
        self.assertEqual(auth.source, "firefox")
        self.assertEqual(auth.xsrf, "example-token")

    def test_rejects_unsupported_browser(self) -> None:
        fake_module = types.SimpleNamespace()
        environment = self.clean_environment()
        environment.update(
            {
                "TENCENT_DOCS_USE_BROWSER_COOKIES": "1",
                "TENCENT_DOCS_BROWSER": "unknown-browser",
            }
        )
        with patch.dict(os.environ, environment, clear=True), patch.dict(
            sys.modules, {"browser_cookie3": fake_module}
        ):
            with self.assertRaisesRegex(TencentDocsError, "不支持浏览器"):
                load_auth(required=True)


if __name__ == "__main__":
    unittest.main()
