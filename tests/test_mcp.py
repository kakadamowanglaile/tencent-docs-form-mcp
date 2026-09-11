"""验证 MCP 工具能够被客户端发现。"""

import unittest

from mcp import Client

from server import mcp


class MCPProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_lists_expected_tools(self) -> None:
        async with Client(mcp, raise_exceptions=True) as client:
            listed = await client.list_tools()

        names = {tool.name for tool in listed.tools}
        self.assertEqual(
            names,
            {
                "tencent_docs_login",
                "tencent_docs_create_form",
                "tencent_docs_create_and_publish_form",
                "tencent_docs_inspect_form",
                "tencent_docs_replace_form_questions",
                "tencent_docs_publish_form",
                "tencent_docs_build_and_publish_form",
            },
        )
