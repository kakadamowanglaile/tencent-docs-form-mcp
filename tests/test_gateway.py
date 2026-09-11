"""验证官方工具和扩展工具会合并为一个 MCP。"""

import unittest
from unittest.mock import patch

from mcp.types import Tool

from gateway import _list_tools


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
