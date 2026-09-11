"""腾讯文档官方 MCP 的轻量客户端。

官方工具的名称、说明和 JSON Schema 始终从 tools/list 读取，
本项目不保存用户 Token，也不在日志或异常中输出 Token。
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import httpx2
from mcp.types import CallToolResult, Tool

from tencent_form import BASE_URL, TencentDocsError, TencentFormClient, load_auth

OFFICIAL_MCP_URL = "https://docs.qq.com/openapi/mcp"
OFFICIAL_TOKEN_ENV = "TENCENT_DOCS_MCP_TOKEN"
OFFICIAL_SPACE_ENV = "TENCENT_DOCS_SPACE_ID"
TOOLS_CACHE_SECONDS = 600


class TencentOfficialMCPClient:
    """动态转发腾讯文档官方 MCP。"""

    def __init__(self, timeout: float = 60.0):
        self.timeout = timeout
        self._token: str | None = None
        self._token_source = ""
        self._tools: list[Tool] | None = None
        self._tool_names: set[str] = set()
        self._tools_loaded_at = 0.0
        self._lock = threading.RLock()

    @property
    def token_source(self) -> str:
        return self._token_source or "not-loaded"

    def _load_token(self) -> str:
        configured = os.environ.get(OFFICIAL_TOKEN_ENV, "").strip()
        if configured:
            self._token_source = "environment"
            return configured

        auth = load_auth(required=True)
        web = TencentFormClient(auth, timeout=self.timeout)
        spaces_result = web._ensure_success(
            web._request_json(
                "/api/v6/spacequery/mcp/list",
                method="POST",
                body={"num": 0},
                referer=BASE_URL + "/open/auth/mcp.html",
            ),
            "读取官方 MCP 授权空间",
        )
        spaces = (spaces_result.get("result") or {}).get("spaceInfos") or []
        if not isinstance(spaces, list) or not spaces:
            raise TencentDocsError("当前账号没有可用于官方 MCP 的空间。")

        configured_space = os.environ.get(OFFICIAL_SPACE_ENV, "").strip()
        if configured_space:
            selected = next(
                (
                    item
                    for item in spaces
                    if isinstance(item, dict) and str(item.get("wikiId") or "") == configured_space
                ),
                None,
            )
            if selected is None:
                raise TencentDocsError(
                    f"{OFFICIAL_SPACE_ENV} 与当前账号的 MCP 授权空间不匹配。"
                )
        elif len(spaces) == 1:
            selected = spaces[0]
        else:
            raise TencentDocsError(
                f"当前账号有 {len(spaces)} 个可授权空间，"
                f"请在本机设置 {OFFICIAL_SPACE_ENV} 后重启 MCP。"
            )

        space_id = str((selected or {}).get("wikiId") or "")
        if not space_id:
            raise TencentDocsError("官方 MCP 授权空间缺少 wikiId。")
        token_result = web._request_json(
            "/oauth/v2/space/create_secret",
            params={"space_id": space_id, "refresh": 0},
            referer=BASE_URL + "/open/auth/mcp.html",
        )
        if token_result.get("ret") != 0:
            message = token_result.get("msg") or "未提供错误说明"
            raise TencentDocsError(f"获取官方 MCP Token 失败：{message}。")
        token_data = token_result.get("data") or {}
        token = str(token_data.get("space_secret") or "").strip()
        if not token:
            if token_data.get("expired"):
                raise TencentDocsError(
                    "官方 MCP Token 已过期，请在腾讯文档 MCP Token 页面手动刷新。"
                )
            raise TencentDocsError("腾讯文档未返回官方 MCP Token。")
        self._token_source = f"tencent-docs-{auth.source}"
        return token

    def _authorization(self) -> str:
        with self._lock:
            if not self._token:
                self._token = self._load_token()
            return self._token

    def _rpc(self, method: str, params: dict[str, Any], request_id: int) -> dict[str, Any]:
        headers = {
            "Authorization": self._authorization(),
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        try:
            response = httpx2.post(
                OFFICIAL_MCP_URL,
                headers=headers,
                json={
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "method": method,
                    "params": params,
                },
                timeout=self.timeout,
                follow_redirects=True,
            )
        except Exception as exc:
            raise TencentDocsError("无法连接腾讯文档官方 MCP。") from exc
        if response.status_code in {401, 403}:
            raise TencentDocsError(
                "腾讯文档官方 MCP 拒绝了授权，请重新登录或更新 MCP Token。"
            )
        if response.status_code != 200:
            raise TencentDocsError(
                f"腾讯文档官方 MCP 请求失败，HTTP {response.status_code}。"
            )
        try:
            payload = response.json()
        except ValueError:
            try:
                data_line = next(
                    line[6:]
                    for line in response.text.splitlines()
                    if line.startswith("data: ")
                )
                payload = json.loads(data_line)
            except Exception as exc:
                raise TencentDocsError(
                    "腾讯文档官方 MCP 返回了无法解析的数据。"
                ) from exc
        if not isinstance(payload, dict):
            raise TencentDocsError("腾讯文档官方 MCP 返回的数据结构异常。")
        error = payload.get("error")
        if isinstance(error, dict):
            code = error.get("code")
            message = error.get("message") or "未提供错误说明"
            raise TencentDocsError(f"官方 MCP 错误 {code}：{message}。")
        result = payload.get("result")
        if not isinstance(result, dict):
            raise TencentDocsError("腾讯文档官方 MCP 没有返回 result。")
        return result

    def list_tools(self, force_refresh: bool = False) -> list[Tool]:
        with self._lock:
            cache_fresh = (
                self._tools is not None
                and time.monotonic() - self._tools_loaded_at < TOOLS_CACHE_SECONDS
            )
            if cache_fresh and not force_refresh:
                return list(self._tools or [])
            result = self._rpc("tools/list", {}, 1)
            raw_tools = result.get("tools") or []
            if not isinstance(raw_tools, list):
                raise TencentDocsError("官方 MCP tools/list 未返回工具列表。")
            tools = [Tool.model_validate(item) for item in raw_tools]
            self._tools = tools
            self._tool_names = {tool.name for tool in tools}
            self._tools_loaded_at = time.monotonic()
            return list(tools)

    def has_tool(self, name: str) -> bool:
        if not self._tools:
            self.list_tools()
        return name in self._tool_names

    def call_tool(self, name: str, arguments: dict[str, Any]) -> CallToolResult:
        result = self._rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
            2,
        )
        return CallToolResult.model_validate(result)


official_client = TencentOfficialMCPClient()
