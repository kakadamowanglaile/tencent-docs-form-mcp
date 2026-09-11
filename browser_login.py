"""在 Windows 上完成一次浏览器登录，并安全保存给 MCP 使用。"""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from tencent_form import TencentDocsError, save_windows_auth


BROWSER_ORDER = ("chrome", "edge", "brave", "vivaldi", "chromium")


def configure_console_encoding() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")


def browser_candidates(name: str) -> list[Path]:
    local = Path(os.environ.get("LOCALAPPDATA", "C:/"))
    program_files = Path(os.environ.get("ProgramFiles", "C:/Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)"))
    known = {
        "chrome": [
            program_files / "Google/Chrome/Application/chrome.exe",
            program_files_x86 / "Google/Chrome/Application/chrome.exe",
            local / "Google/Chrome/Application/chrome.exe",
        ],
        "edge": [
            program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
            program_files / "Microsoft/Edge/Application/msedge.exe",
        ],
        "brave": [
            program_files / "BraveSoftware/Brave-Browser/Application/brave.exe",
            local / "BraveSoftware/Brave-Browser/Application/brave.exe",
        ],
        "vivaldi": [
            local / "Vivaldi/Application/vivaldi.exe",
            program_files / "Vivaldi/Application/vivaldi.exe",
        ],
        "chromium": [
            local / "Chromium/Application/chrome.exe",
            program_files / "Chromium/Application/chrome.exe",
        ],
    }
    command_names = {
        "chrome": "chrome",
        "edge": "msedge",
        "brave": "brave",
        "vivaldi": "vivaldi",
        "chromium": "chromium",
    }
    found = shutil.which(command_names[name])
    return ([Path(found)] if found else []) + known[name]


def find_browser(requested: str) -> tuple[str, Path]:
    names = BROWSER_ORDER if requested == "auto" else (requested,)
    for name in names:
        for candidate in browser_candidates(name):
            if candidate.is_file():
                return name, candidate.resolve()
    choices = "、".join(BROWSER_ORDER)
    raise TencentDocsError(f"没有找到可用浏览器。支持自动检测：{choices}。")


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def browser_websocket(port: int) -> str | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1) as response:
            return json.loads(response.read().decode("utf-8")).get("webSocketDebuggerUrl")
    except Exception:
        return None


def read_cookies(websocket_url: str) -> list[dict]:
    try:
        import websocket
    except ImportError as exc:
        raise TencentDocsError("缺少 websocket-client，请重新执行安装脚本。") from exc
    connection = websocket.create_connection(websocket_url, timeout=2, suppress_origin=True)
    try:
        connection.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
        while True:
            message = json.loads(connection.recv())
            if message.get("id") == 1:
                return (message.get("result") or {}).get("cookies") or []
    finally:
        connection.close()


def close_browser(websocket_url: str) -> None:
    try:
        import websocket

        connection = websocket.create_connection(websocket_url, timeout=2, suppress_origin=True)
        connection.send(json.dumps({"id": 2, "method": "Browser.close"}))
        connection.close()
    except Exception:
        pass


def cookie_header_for_docs(cookies: list[dict]) -> str:
    selected = []
    for cookie in cookies:
        domain = str(cookie.get("domain") or "").lstrip(".").lower()
        if domain and "docs.qq.com".endswith(domain):
            selected.append(f"{cookie['name']}={cookie['value']}")
    return "; ".join(selected)


def login_with_browser(
    requested_browser: str = "auto",
    timeout: int = 300,
    profile_dir: str | None = None,
) -> dict[str, object]:
    """完成一次可见的 Windows 浏览器登录，检测成功后立即关闭窗口。"""
    if platform.system() != "Windows":
        raise TencentDocsError("这个自动登录工具目前只支持 Windows。")
    browser_name, executable = find_browser(requested_browser)
    base = Path(os.environ["LOCALAPPDATA"]) / "TencentDocsFormMCP"
    configured_profile = profile_dir or os.environ.get("TENCENT_DOCS_LOGIN_PROFILE_DIR")
    profile = (
        Path(configured_profile).resolve()
        if configured_profile
        else base / f"{browser_name}-profile"
    )
    profile.mkdir(parents=True, exist_ok=True)
    port = free_port()
    process = subprocess.Popen(
        [
            str(executable),
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile}",
            "--no-first-run",
            "--no-default-browser-check",
            "https://docs.qq.com/",
        ]
    )
    deadline = time.monotonic() + max(10, timeout)
    websocket_url = None
    try:
        while time.monotonic() < deadline:
            websocket_url = websocket_url or browser_websocket(port)
            if websocket_url:
                try:
                    raw_cookie = cookie_header_for_docs(read_cookies(websocket_url))
                except Exception:
                    time.sleep(0.5)
                    continue
                if "TOK=" in raw_cookie:
                    save_windows_auth(raw_cookie)
                    return {"browser": browser_name, "saved": True, "window_closed": True}
            if process.poll() is not None:
                raise TencentDocsError("登录窗口已关闭，但尚未检测到腾讯文档登录。")
            time.sleep(0.5)
        raise TencentDocsError("等待登录超时，请重新运行登录工具。")
    finally:
        if websocket_url:
            close_browser(websocket_url)
        if process.poll() is None:
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.terminate()


def main() -> int:
    configure_console_encoding()
    parser = argparse.ArgumentParser(description="打开浏览器登录腾讯文档，成功后自动关闭窗口。")
    parser.add_argument("--browser", choices=("auto", *BROWSER_ORDER), default="auto")
    parser.add_argument("--timeout", type=int, default=300, help="等待登录的最长秒数。")
    parser.add_argument("--profile-dir", help=argparse.SUPPRESS)
    args = parser.parse_args()
    try:
        result = login_with_browser(args.browser, args.timeout, args.profile_dir)
        print(f"登录成功，{result['browser']} 窗口已自动关闭。")
        return 0
    except TencentDocsError as exc:
        print(f"登录失败：{exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"登录失败：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
