"""WorkBuddy CLI 连接器与通用命令行入口。"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any

from mcp import Client

from server import mcp
from tencent_form import SUPPORTED_BROWSERS, TencentDocsError, load_auth


LOGIN_URL = "https://docs.qq.com/desktop"


def _configure_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def _state_dir() -> Path:
    configured = os.environ.get("TENCENT_DOCS_CONNECTOR_STATE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home()))
        return base / "TencentDocsExtensions"
    if system == "Darwin":
        return Path.home() / "Library" / "Application Support" / "TencentDocsExtensions"
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return base / "tencent-docs-extensions"


def _logout_marker() -> Path:
    return _state_dir() / "logged-out"


def _is_logged_out() -> bool:
    return _logout_marker().is_file()


def _set_logged_out(value: bool) -> None:
    marker = _logout_marker()
    if value:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("1\n", encoding="utf-8")
    elif marker.exists():
        marker.unlink()


def _browser_order() -> list[str]:
    requested = os.environ.get("TENCENT_DOCS_BROWSER", "").strip().lower()
    defaults = ["chrome", "edge", "firefox", "brave", "vivaldi", "chromium"]
    if requested in SUPPORTED_BROWSERS:
        return [requested, *[name for name in defaults if name != requested]]
    return defaults


def _select_browser_auth() -> str | None:
    """选择一个已登录腾讯文档的浏览器，不保存 Cookie。"""
    old_opt_in = os.environ.get("TENCENT_DOCS_USE_BROWSER_COOKIES")
    old_browser = os.environ.get("TENCENT_DOCS_BROWSER")
    os.environ["TENCENT_DOCS_USE_BROWSER_COOKIES"] = "1"
    for browser in _browser_order():
        os.environ["TENCENT_DOCS_BROWSER"] = browser
        try:
            load_auth(required=True)
        except TencentDocsError:
            continue
        return browser
    if old_opt_in is None:
        os.environ.pop("TENCENT_DOCS_USE_BROWSER_COOKIES", None)
    else:
        os.environ["TENCENT_DOCS_USE_BROWSER_COOKIES"] = old_opt_in
    if old_browser is None:
        os.environ.pop("TENCENT_DOCS_BROWSER", None)
    else:
        os.environ["TENCENT_DOCS_BROWSER"] = old_browser
    return None


def _json_print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


async def _list_tools() -> dict[str, Any]:
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.list_tools()
    tools = [tool.model_dump(by_alias=True, exclude_none=True) for tool in result.tools]
    return {"count": len(tools), "tools": tools}


def _business_result(result: Any) -> Any:
    if result.is_error:
        messages = [getattr(item, "text", "") for item in result.content]
        raise TencentDocsError("\n".join(message for message in messages if message))
    structured = getattr(result, "structured_content", None)
    if structured is not None:
        if isinstance(structured, dict) and set(structured) == {"result"}:
            return structured["result"]
        return structured
    texts = [getattr(item, "text", "") for item in result.content]
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return {"text": texts[0]}
    return {"content": texts}


async def _call_tool(name: str, arguments: dict[str, Any]) -> Any:
    if _is_logged_out():
        raise TencentDocsError("连接器已退出，请先重新连接腾讯文档。")
    if not name.startswith("tencent_docs_openapi_") and name != "tencent_docs_login":
        _select_browser_auth()
    async with Client(mcp, raise_exceptions=True) as client:
        result = await client.call_tool(name, arguments)
    return _business_result(result)


def _parse_arguments(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise TencentDocsError(f"参数 JSON 无效：{exc.msg}。") from exc
    if not isinstance(value, dict):
        raise TencentDocsError("参数 JSON 必须是对象。")
    return value


def _auth_command(action: str) -> int:
    if action == "login":
        _set_logged_out(False)
        print(f"请在浏览器登录腾讯文档： {LOGIN_URL} ")
        return 0
    if action == "logout":
        _set_logged_out(True)
        print("Logged out. 连接器已停止使用浏览器登录态；不会退出浏览器中的腾讯文档账号。")
        return 0
    if _is_logged_out():
        print("Logged out")
        return 1
    browser = _select_browser_auth()
    if browser:
        print(f"Logged in ({browser})")
        return 0
    print("Logged out. 请在浏览器登录腾讯文档。")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="腾讯文档扩展工具（社区版）")
    commands = parser.add_subparsers(dest="command", required=True)

    tools = commands.add_parser("tools", help="列出全部可用工具和参数")
    tools.add_argument("--json", action="store_true", help="输出 JSON")

    call = commands.add_parser("call", help="调用一个腾讯文档扩展工具")
    call.add_argument("name", help="工具名")
    call.add_argument("--json", default="{}", metavar="OBJECT", help="JSON 对象参数")

    auth = commands.add_parser("auth", help="管理 WorkBuddy 连接状态")
    auth.add_argument("action", choices=("login", "status", "logout"))
    return parser


def main(argv: list[str] | None = None) -> int:
    _configure_console()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "auth":
            return _auth_command(args.action)
        if args.command == "tools":
            payload = asyncio.run(_list_tools())
            if args.json:
                _json_print(payload)
            else:
                for tool in payload["tools"]:
                    print(f"{tool['name']}\t{tool.get('description', '')}")
            return 0
        payload = asyncio.run(_call_tool(args.name, _parse_arguments(args.json)))
        _json_print(payload)
        return 0
    except (TencentDocsError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"执行失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
