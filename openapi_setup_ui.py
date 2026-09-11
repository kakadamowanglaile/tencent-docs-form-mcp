"""腾讯文档 Open API 的本机傻瓜式授权页面。"""

from __future__ import annotations

import html
import secrets
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from openapi_auth import (
    DEFAULT_REDIRECT_URI,
    authorize_interactively,
    configure_openapi_app,
    load_openapi_profile,
)
from tencent_form import TencentDocsError


SETUP_PORTS = tuple(range(49670, 49680))
MAX_FORM_BYTES = 16 * 1024

STYLE = """
:root { color-scheme: light dark; font-family: system-ui,-apple-system,"Segoe UI",sans-serif; }
* { box-sizing: border-box; }
body { display:grid; min-height:100vh; margin:0; place-items:center; background:#f4f7fb; color:#172033; }
main { width:min(38rem,calc(100% - 2rem)); padding:2rem; border:1px solid #dce3ef; border-radius:1rem; background:#fff; box-shadow:0 1rem 3rem rgb(23 32 51 / 10%); }
h1 { margin:0 0 .75rem; font-size:1.6rem; }
p { line-height:1.7; }
.muted { color:#5f6b7d; font-size:.92rem; }
.notice { padding:.8rem 1rem; border-radius:.6rem; background:#fff3cd; color:#664d03; }
.success { padding:.8rem 1rem; border-radius:.6rem; background:#dff6e7; color:#155b32; }
label { display:block; margin:1rem 0 .4rem; font-weight:650; }
input { width:100%; padding:.75rem; border:1px solid #b8c3d4; border-radius:.55rem; font:inherit; background:transparent; color:inherit; }
button { width:100%; margin-top:1.25rem; padding:.85rem 1rem; border:0; border-radius:.6rem; background:#146ef5; color:#fff; font:inherit; font-weight:700; cursor:pointer; }
a { color:#146ef5; }
code { overflow-wrap:anywhere; }
details { margin-top:1rem; }
@media (prefers-color-scheme:dark) { body{background:#10141d;color:#edf3ff} main{border-color:#30394a;background:#1a202c} .muted{color:#aeb9ca} .notice{background:#3c3214;color:#ffe69c} .success{background:#153c28;color:#b9f6cf} }
""".strip()


@dataclass
class SetupUIState:
    csrf_token: str
    status: str = "idle"
    error: str = ""
    lock: threading.Lock = field(default_factory=threading.Lock)
    shutdown_scheduled: bool = False


_ui_lock = threading.Lock()
_ui_server: ThreadingHTTPServer | None = None
_ui_thread: threading.Thread | None = None
_ui_state: SetupUIState | None = None


def _safe_profile():
    try:
        return load_openapi_profile(required=False)
    except TencentDocsError:
        return None


def _mask_client_id(value: str) -> str:
    if len(value) <= 8:
        return "••••"
    return value[:4] + "••••" + value[-4:]


def _page(state: SetupUIState, *, edit: bool = False) -> str:
    profile = _safe_profile()
    with state.lock:
        status = state.status
        error = state.error
    refresh = '<meta http-equiv="refresh" content="2">' if status == "running" else ""
    notice = f'<p class="notice">{html.escape(error)}</p>' if error else ""

    if status == "running":
        content = """
        <h1>等待腾讯文档授权</h1>
        <p>腾讯官方授权页已经打开，请在该页面确认授权。</p>
        <p class="muted">完成后本页会自动更新，不需要复制授权码。</p>
        """
    elif status == "success":
        content = """
        <h1>授权成功</h1>
        <p class="success">Token 已保存到当前电脑的系统密钥库。</p>
        <p>现在可以关闭此页面，返回 AI 客户端使用腾讯文档。</p>
        """
    elif profile is None or not profile.app_configured or edit:
        existing_id = html.escape(profile.client_id if profile else "", quote=True)
        redirect_uri = html.escape(
            profile.redirect_uri if profile else DEFAULT_REDIRECT_URI, quote=True
        )
        content = f"""
        <h1>连接腾讯文档 Open API</h1>
        <p>首次使用只需填写一次你自己的开放平台应用信息。</p>
        {notice}
        <form method="post" action="/configure" autocomplete="off">
          <input type="hidden" name="csrf_token" value="{state.csrf_token}">
          <label for="client_id">Client ID</label>
          <input id="client_id" name="client_id" value="{existing_id}" required maxlength="300" spellcheck="false">
          <label for="client_secret">Client Secret</label>
          <input id="client_secret" name="client_secret" type="password" required maxlength="2000" autocomplete="new-password">
          <details>
            <summary>高级设置</summary>
            <label for="redirect_uri">HTTPS 回调地址</label>
            <input id="redirect_uri" name="redirect_uri" value="{redirect_uri}" required maxlength="1000" spellcheck="false">
          </details>
          <button type="submit">保存并授权</button>
        </form>
        <p class="muted">Client Secret 只发送到本机 127.0.0.1，不会进入 AI 对话或 GitHub。</p>
        """
    else:
        action = "重新授权" if profile.authorized else "授权腾讯文档"
        authorized = (
            '<p class="success">当前电脑已经保存过授权。</p>'
            if profile.authorized
            else ""
        )
        content = f"""
        <h1>腾讯文档授权</h1>
        {authorized}
        {notice}
        <p>应用：<code>{html.escape(_mask_client_id(profile.client_id))}</code></p>
        <form method="post" action="/authorize">
          <input type="hidden" name="csrf_token" value="{state.csrf_token}">
          <button type="submit">{action}</button>
        </form>
        <p class="muted"><a href="/?edit=1">更换开放平台应用</a></p>
        """

    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer">{refresh}<title>腾讯文档授权</title><link rel="stylesheet" href="/style.css"></head>
<body><main>{content}</main></body></html>"""


def _start_authorization(state: SetupUIState) -> None:
    with state.lock:
        if state.status == "running":
            return
        state.status = "running"
        state.error = ""

    def worker() -> None:
        try:
            authorize_interactively()
            # 如果设置页由正在运行的 MCP 打开，立即更新该进程的客户端缓存。
            from openapi_client import load_openapi_credentials, openapi_client

            openapi_client.credentials = load_openapi_credentials(required=True)
        except TencentDocsError as exc:
            with state.lock:
                state.status = "error"
                state.error = str(exc)
        except Exception:
            with state.lock:
                state.status = "error"
                state.error = "授权程序发生异常，请重启 AI 客户端后重试。"
        else:
            with state.lock:
                state.status = "success"

    threading.Thread(target=worker, daemon=True, name="tencent-docs-oauth").start()


def _handler_for(state: SetupUIState):
    class SetupHandler(BaseHTTPRequestHandler):
        server_version = "TencentDocsSetup/1"
        sys_version = ""

        def _request_is_local(self) -> bool:
            port = int(self.server.server_address[1])
            expected = {f"127.0.0.1:{port}", f"localhost:{port}"}
            if self.headers.get("Host", "") not in expected:
                return False
            origin = self.headers.get("Origin", "")
            return not origin or origin in {
                f"http://127.0.0.1:{port}",
                f"http://localhost:{port}",
            }

        def _headers(self, status: int, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'none'; style-src 'self'; form-action 'self'; "
                "base-uri 'none'; frame-ancestors 'none'",
            )
            self.end_headers()

        def _send_text(self, status: int, text: str) -> None:
            body = text.encode("utf-8")
            self._headers(status, "text/plain; charset=utf-8", len(body))
            self.wfile.write(body)

        def _redirect_home(self) -> None:
            self.send_response(303)
            self.send_header("Location", "/")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()

        def _form(self) -> dict[str, str]:
            raw_length = self.headers.get("Content-Length", "0")
            try:
                length = int(raw_length)
            except ValueError as exc:
                raise TencentDocsError("请求长度无效。") from exc
            if length <= 0 or length > MAX_FORM_BYTES:
                raise TencentDocsError("请求内容为空或过大。")
            try:
                raw = self.rfile.read(length).decode("utf-8")
            except UnicodeDecodeError as exc:
                raise TencentDocsError("请求编码无效。") from exc
            parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
            return {key: values[0] for key, values in parsed.items() if values}

        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._request_is_local():
                self._send_text(403, "拒绝非本机请求。")
                return
            parsed = urllib.parse.urlparse(self.path)
            if parsed.path == "/style.css":
                body = STYLE.encode("utf-8")
                self._headers(200, "text/css; charset=utf-8", len(body))
                self.wfile.write(body)
                return
            if parsed.path != "/":
                self._send_text(404, "页面不存在。")
                return
            body = _page(
                state,
                edit=urllib.parse.parse_qs(parsed.query).get("edit") == ["1"],
            ).encode("utf-8")
            self._headers(200, "text/html; charset=utf-8", len(body))
            self.wfile.write(body)
            with state.lock:
                should_shutdown = (
                    state.status == "success" and not state.shutdown_scheduled
                )
                if should_shutdown:
                    state.shutdown_scheduled = True
            if should_shutdown:
                threading.Timer(5, self.server.shutdown).start()

        def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
            if not self._request_is_local():
                self._send_text(403, "拒绝非本机请求。")
                return
            if not self.headers.get("Content-Type", "").startswith(
                "application/x-www-form-urlencoded"
            ):
                self._send_text(415, "只接受表单请求。")
                return
            try:
                form = self._form()
                if not secrets.compare_digest(
                    form.get("csrf_token", ""), state.csrf_token
                ):
                    raise TencentDocsError("页面令牌无效，请重新打开授权窗口。")
                if self.path == "/configure":
                    configure_openapi_app(
                        form.get("client_id", ""),
                        form.get("client_secret", ""),
                        form.get("redirect_uri", ""),
                    )
                elif self.path != "/authorize":
                    self._send_text(404, "页面不存在。")
                    return
                _start_authorization(state)
            except TencentDocsError as exc:
                with state.lock:
                    state.status = "error"
                    state.error = str(exc)
            self._redirect_home()

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return SetupHandler


def _serve(server: ThreadingHTTPServer) -> None:
    try:
        server.serve_forever()
    finally:
        server.server_close()


def open_setup_ui(
    *,
    browser_opener: Callable[[str], Any] = webbrowser.open,
    block: bool = False,
) -> dict[str, Any]:
    """启动本机设置页；MCP 调用立即返回，命令行调用可等待完成。"""
    global _ui_server, _ui_thread, _ui_state
    with _ui_lock:
        if _ui_thread is None or not _ui_thread.is_alive():
            server = None
            for port in SETUP_PORTS:
                try:
                    server = ThreadingHTTPServer(
                        ("127.0.0.1", port), BaseHTTPRequestHandler
                    )
                    break
                except OSError:
                    continue
            if server is None:
                raise TencentDocsError(
                    "本机设置端口 49670-49679 均被占用，请关闭占用程序后重试。"
                )
            state = SetupUIState(csrf_token=secrets.token_urlsafe(32))
            server.RequestHandlerClass = _handler_for(state)
            thread = threading.Thread(
                target=_serve,
                args=(server,),
                daemon=True,
                name="tencent-docs-setup-ui",
            )
            _ui_server, _ui_thread, _ui_state = server, thread, state
            thread.start()
        assert _ui_server is not None and _ui_thread is not None
        url = f"http://127.0.0.1:{int(_ui_server.server_address[1])}/"
        thread = _ui_thread
    if browser_opener(url) is False:
        stop_setup_ui()
        raise TencentDocsError(f"无法自动打开浏览器，请手动打开 {url}")
    profile = _safe_profile()
    result = {
        "setup_ui_opened": True,
        "local_only": True,
        "app_configured": bool(profile and profile.app_configured),
        "authorized": bool(profile and profile.authorized),
    }
    if block:
        try:
            while thread.is_alive():
                thread.join(timeout=0.5)
        except KeyboardInterrupt:
            stop_setup_ui()
    return result


def stop_setup_ui() -> None:
    """停止当前进程启动的设置页。"""
    global _ui_server, _ui_thread, _ui_state
    with _ui_lock:
        server, thread = _ui_server, _ui_thread
        _ui_server = None
        _ui_thread = None
        _ui_state = None
    if server is not None and thread is not None and thread.is_alive():
        server.shutdown()
    if server is not None:
        server.server_close()
    if thread is not None and thread is not threading.current_thread():
        thread.join(timeout=2)


def main() -> int:
    try:
        open_setup_ui(block=True)
        return 0
    except TencentDocsError as exc:
        print(f"无法打开授权窗口：{exc}")
        time.sleep(3)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
