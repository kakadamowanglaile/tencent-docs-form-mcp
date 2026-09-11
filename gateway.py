"""统一腾讯文档 MCP：官方工具动态代理 + 本项目扩展工具。"""

from __future__ import annotations

import asyncio

from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    CallToolRequestParams,
    CallToolResult,
    ListToolsResult,
    TextContent,
)

from official_mcp import official_client
from server import mcp as extension_mcp
from tencent_form import TencentDocsError


async def _list_tools(_context, _params) -> ListToolsResult:
    extension_tools = await extension_mcp.list_tools()
    try:
        official_tools = await asyncio.to_thread(official_client.list_tools)
    except TencentDocsError:
        # 登录前仍然让客户端看到登录、状态和收集表扩展工具。
        official_tools = []

    extension_names = {tool.name for tool in extension_tools}
    collisions = sorted(tool.name for tool in official_tools if tool.name in extension_names)
    if collisions:
        raise RuntimeError("官方工具与扩展工具重名：" + "、".join(collisions))
    return ListToolsResult(tools=[*official_tools, *extension_tools])


async def _call_tool(_context, params: CallToolRequestParams) -> CallToolResult:
    name = params.name
    arguments = params.arguments or {}
    extension_names = {tool.name for tool in await extension_mcp.list_tools()}
    if name in extension_names:
        return await extension_mcp.call_tool(name, arguments)
    try:
        if not await asyncio.to_thread(official_client.has_tool, name):
            return CallToolResult(
                content=[TextContent(type="text", text=f"未知工具：{name}。")],
                is_error=True,
            )
        return await asyncio.to_thread(official_client.call_tool, name, arguments)
    except TencentDocsError as exc:
        return CallToolResult(
            content=[TextContent(type="text", text=str(exc))],
            is_error=True,
        )


gateway = Server(
    "tencent-docs-complete",
    version="0.3.0",
    title="腾讯文档完整 MCP",
    description="动态代理官方 MCP，并补充未打包的正式 Open API 与收集表扩展。",
    on_list_tools=_list_tools,
    on_call_tool=_call_tool,
)


async def _run() -> None:
    async with stdio_server() as (read_stream, write_stream):
        await gateway.run(
            read_stream,
            write_stream,
            gateway.create_initialization_options(),
        )


if __name__ == "__main__":
    asyncio.run(_run())
