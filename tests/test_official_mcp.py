"""验证官方 MCP 动态工具代理。"""

import os
import unittest
from unittest.mock import patch

from official_mcp import TencentOfficialMCPClient


class FakeResponse:
    status_code = 200

    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class OfficialMCPTests(unittest.TestCase):
    def test_lists_live_schema_and_caches_it(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {
                "tools": [
                    {
                        "name": "doc.example",
                        "description": "example",
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                ]
            },
        }
        with patch.dict(
            os.environ, {"TENCENT_DOCS_MCP_TOKEN": "secret"}, clear=False
        ), patch(
            "official_mcp.httpx2.post", return_value=FakeResponse(payload)
        ) as post:
            client = TencentOfficialMCPClient()
            first = client.list_tools()
            second = client.list_tools()

        self.assertEqual([tool.name for tool in first], ["doc.example"])
        self.assertEqual([tool.name for tool in second], ["doc.example"])
        self.assertEqual(post.call_count, 1)
        self.assertEqual(post.call_args.kwargs["headers"]["Authorization"], "secret")

    def test_converts_remote_tool_result(self) -> None:
        payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "result": {"content": [{"type": "text", "text": "ok"}], "isError": False},
        }
        with patch.dict(
            os.environ, {"TENCENT_DOCS_MCP_TOKEN": "secret"}, clear=False
        ), patch("official_mcp.httpx2.post", return_value=FakeResponse(payload)):
            result = TencentOfficialMCPClient().call_tool("doc.example", {"x": 1})

        self.assertFalse(result.is_error)
        self.assertEqual(result.content[0].text, "ok")
