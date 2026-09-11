"""验证官方工具和扩展工具会合并为一个 MCP。"""

import unittest
from unittest.mock import patch

from mcp.types import Tool

from gateway import _call_tool, _list_tools
from tencent_form import TencentDocsError


class GatewayTests(unittest.IsolatedAsyncioTestCase):
    async def test_merges_official_and_extension_tools(self) -> None:
        remote = Tool(
            name="doc.example",
            description="example",
            input_schema={"type": "object", "properties": {}},
        )
        with patch("gateway.official_client.list_tools", return_value=[remote]):
            result = await _list_tools(None, None)

        names = {tool.name for tool in result.tools}
        self.assertIn("doc.example", names)
        self.assertIn("tencent_docs_create_and_publish_form", names)

    async def test_extension_tool_error_is_returned_as_tool_result(self) -> None:
        params = type(
            "Params",
            (),
            {"name": "tencent_docs_list_versions", "arguments": {"file_id": "abc"}},
        )()
        with patch(
            "server._list_versions_sync",
            side_effect=TencentDocsError("该文件类型不支持版本历史。"),
        ):
            result = await _call_tool(None, params)

        self.assertTrue(result.is_error)
        self.assertIn("该文件类型不支持版本历史。", result.content[0].text)
