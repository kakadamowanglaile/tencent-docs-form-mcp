"""验证任意 MCP 客户端可以发现并调用正式 Open API 工具。"""

import json
import time
import unittest
from unittest.mock import AsyncMock, patch

from mcp import Client

from server import mcp


class OpenAPIMCPTests(unittest.IsolatedAsyncioTestCase):
    async def test_calls_read_only_openapi_tool_through_mcp(self) -> None:
        with patch(
            "server.openapi_client.get_unread_count",
            new=AsyncMock(return_value={"ret": 0, "data": {"count": 3}}),
        ):
            async with Client(mcp, raise_exceptions=True) as client:
                result = await client.call_tool(
                    "tencent_docs_openapi_get_unread_count", {}
                )

        payload = json.loads(result.content[0].text)
        self.assertEqual(payload["data"]["count"], 3)

    async def test_form_deadline_maps_to_official_timestamp(self) -> None:
        deadline = int(time.time()) + 3600
        mocked = AsyncMock(return_value={"ret": 0, "msg": "Succeed"})
        with patch("server.openapi_client.set_form_release", new=mocked):
            async with Client(mcp, raise_exceptions=True) as client:
                await client.call_tool(
                    "tencent_docs_openapi_set_form_release",
                    {"form_id": "form", "mode": "deadline", "end_time": deadline},
                )

        mocked.assert_awaited_once_with("form", deadline)

    async def test_transfer_ownership_requires_exact_confirmation(self) -> None:
        mocked = AsyncMock(return_value={"ret": 0})
        with patch("server.openapi_client.transfer_ownership", new=mocked):
            async with Client(mcp, raise_exceptions=False) as client:
                result = await client.call_tool(
                    "tencent_docs_openapi_transfer_ownership",
                    {
                        "file_id": "file",
                        "owner_open_id": "user",
                        "confirmation": "确认",
                    },
                )

        self.assertTrue(result.is_error)
        mocked.assert_not_awaited()
