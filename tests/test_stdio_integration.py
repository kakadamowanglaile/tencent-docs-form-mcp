"""跨进程验证 Codex、Claude 等客户端使用的 stdio MCP。"""

import json
import sys
import unittest
from pathlib import Path

from mcp import Client, StdioServerParameters


class StdioIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_gateway_exposes_openapi_tools_over_stdio(self) -> None:
        root = Path(__file__).resolve().parents[1]
        parameters = StdioServerParameters(
            command=sys.executable,
            args=[str(root / "gateway.py")],
            cwd=root,
        )

        async with Client(parameters, raise_exceptions=True) as client:
            listed = await client.list_tools()
            status = await client.call_tool(
                "tencent_docs_openapi_status", {"validate": False}
            )

        names = {tool.name for tool in listed.tools}
        self.assertIn("tencent_docs_openapi_generate_form_result", names)
        self.assertIn("tencent_docs_openapi_batch_insert_sheet_images", names)
        self.assertFalse(json.loads(status.content[0].text)["configured"])
