"""腾讯文档 Open API 的用户自有应用 OAuth2 授权。

每位用户使用自己的 Client ID 和 Client Secret。凭据保存在当前
操作系统的密钥库中，不写入项目目录。
"""

from __future__ import annotations

import base64
import getpass
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass, replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from tencent_form import TencentDocsError


AUTHORIZE_URL = "https://docs.qq.com/oauth/v2/authorize"
TOKEN_URL = "https://docs.qq.com/oauth/v2/token"
DEFAULT_REDIRECT_URI = (
    "https://kakadamowanglaile.github.io/tencent-docs-form-mcp/"
)
# 保留旧服务名，避免升级后找不到用户已保存的本机凭据。
KEYRING_SERVICE = "tencent-docs-complete-mcp"
KEYRING_METADATA_ACCOUNT = "openapi-metadata"
KEYRING_CLIENT_SECRET_ACCOUNT = "openapi-client-secret"
KEYRING_ACCESS_TOKEN_ACCOUNT = "openapi-access-token"
KEYRING_REFRESH_TOKEN_ACCOUNT = "openapi-refresh-token"
PROFILE_VERSION = 1
# 静态回调页只允许跳回这组专用高位端口，避免成为任意 localhost 跳转器。
CALLBACK_PORTS = tuple(range(49680, 49690))


@dataclass(frozen=True)
class OpenAPIProfile:
    """用户自有腾讯文档应用的本机配置和授权结果。"""

    client_id: str
    client_secret: str
    redirect_uri: str
    open_id: str = ""
    access_token: str = ""
    refresh_token: str = ""
    expires_at: int = 0
    version: int = PROFILE_VERSION

    @property
    def app_configured(self) -> bool:
        return bool(self.client_id and self.client_secret and self.redirect_uri)

    @property
    def authorized(self) -> bool:
        return bool(self.open_id and self.access_token)


def _validate_redirect_uri(value: str) -> str:
    uri = value.strip()
    parsed = urllib.parse.urlparse(uri)
    if parsed.scheme != "https" or not parsed.hostname:
        raise TencentDocsError("腾讯文档 OAuth 回调地址必须是完整的 HTTPS URL。")
    return uri


def _keyring_module():
    try:
        import keyring
        from keyring.errors import KeyringError
    except ImportError as exc:
        raise TencentDocsError("缺少 keyring，请重新执行安装脚本。") from exc
    return keyring, KeyringError


def save_openapi_profile(profile: OpenAPIProfile) -> None:
    """把应用密钥和用户 Token 保存到操作系统密钥库。"""
    keyring, KeyringError = _keyring_module()
    try:
        metadata = {
            "client_id": profile.client_id,
            "redirect_uri": profile.redirect_uri,
            "open_id": profile.open_id,
            "expires_at": profile.expires_at,
            "version": profile.version,
        }
        keyring.set_password(
            KEYRING_SERVICE,
            KEYRING_METADATA_ACCOUNT,
            json.dumps(metadata, ensure_ascii=False, separators=(",", ":")),
        )
        keyring.set_password(
            KEYRING_SERVICE, KEYRING_CLIENT_SECRET_ACCOUNT, profile.client_secret
        )
        _set_or_delete_keyring_value(
            keyring, KEYRING_ACCESS_TOKEN_ACCOUNT, profile.access_token
        )
        _set_or_delete_keyring_value(
            keyring, KEYRING_REFRESH_TOKEN_ACCOUNT, profile.refresh_token
        )
    except KeyringError as exc:
        raise TencentDocsError(
            "无法写入操作系统密钥库；请检查 Windows 凭据管理器、"
            "macOS 钥匙串或 Linux Secret Service。"
        ) from exc


def _set_or_delete_keyring_value(keyring: Any, account: str, value: str) -> None:
    """写入非空值；空值删除已有项，避免在凭据管理器里保留空记录。"""
    if value:
        keyring.set_password(KEYRING_SERVICE, account, value)
    elif keyring.get_password(KEYRING_SERVICE, account) is not None:
        keyring.delete_password(KEYRING_SERVICE, account)


def load_openapi_profile(required: bool = False) -> OpenAPIProfile | None:
    """从操作系统密钥库读取授权配置。"""
    keyring, KeyringError = _keyring_module()
    try:
        raw = keyring.get_password(KEYRING_SERVICE, KEYRING_METADATA_ACCOUNT)
    except KeyringError as exc:
        if required:
            raise TencentDocsError("无法读取操作系统密钥库。") from exc
        return None
    if not raw:
        if required:
            raise TencentDocsError(
                "尚未配置腾讯文档 Open API 应用；请先运行 openapi_setup.py。"
            )
        return None
    try:
        data = json.loads(raw)
        profile = OpenAPIProfile(
            client_id=str(data.get("client_id") or ""),
            client_secret=keyring.get_password(
                KEYRING_SERVICE, KEYRING_CLIENT_SECRET_ACCOUNT
            )
            or "",
            redirect_uri=str(data.get("redirect_uri") or ""),
            open_id=str(data.get("open_id") or ""),
            access_token=keyring.get_password(
                KEYRING_SERVICE, KEYRING_ACCESS_TOKEN_ACCOUNT
            )
            or "",
            refresh_token=keyring.get_password(
                KEYRING_SERVICE, KEYRING_REFRESH_TOKEN_ACCOUNT
            )
            or "",
            expires_at=int(data.get("expires_at") or 0),
            version=int(data.get("version") or 0),
        )
    except (AttributeError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise TencentDocsError(
            "密钥库中的腾讯文档 Open API 配置已损坏，请重新运行 openapi_setup.py。"
        ) from exc
    if profile.version != PROFILE_VERSION:
        raise TencentDocsError("本机 Open API 配置版本不受支持，请重新配置。")
    return profile


def configure_openapi_app(
    client_id: str,
    client_secret: str,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
) -> OpenAPIProfile:
    """保存用户自己的开放平台应用配置。"""
    normalized_id = client_id.strip()
    normalized_secret = client_secret.strip()
    if not normalized_id or not normalized_secret:
        raise TencentDocsError("Client ID 和 Client Secret 不能为空。")
    normalized_redirect = _validate_redirect_uri(redirect_uri)
    current = load_openapi_profile(required=False)
    keep_tokens = bool(
        current
        and current.client_id == normalized_id
        and current.redirect_uri == normalized_redirect
    )
    profile = OpenAPIProfile(
        client_id=normalized_id,
        client_secret=normalized_secret,
        redirect_uri=normalized_redirect,
        open_id=current.open_id if keep_tokens and current else "",
        access_token=current.access_token if keep_tokens and current else "",
        refresh_token=current.refresh_token if keep_tokens and current else "",
        expires_at=current.expires_at if keep_tokens and current else 0,
    )
    save_openapi_profile(profile)
    return profile


def clear_openapi_tokens() -> bool:
    """删除用户 Token，保留用户自己的应用配置。"""
    profile = load_openapi_profile(required=False)
    if profile is None:
        return False
    changed = profile.authorized or bool(profile.refresh_token)
    save_openapi_profile(
        replace(
            profile,
            open_id="",
            access_token="",
            refresh_token="",
            expires_at=0,
        )
    )
    return changed


def update_saved_openapi_tokens(
    *,
    client_id: str,
    open_id: str,
    access_token: str,
    refresh_token: str | None = None,
    expires_in: int | None = None,
) -> bool:
    """在 Token 换取或刷新后更新密钥库。"""
    profile = load_openapi_profile(required=False)
    if profile is None or profile.client_id != client_id:
        return False
    saved = replace(
        profile,
        open_id=open_id,
        access_token=access_token,
        refresh_token=refresh_token if refresh_token is not None else profile.refresh_token,
        expires_at=(int(time.time()) + int(expires_in)) if expires_in else profile.expires_at,
    )
    save_openapi_profile(saved)
    return True


def _encode_state(nonce: str, port: int) -> str:
    data = json.dumps(
        {"version": 1, "nonce": nonce, "port": port},
        separators=(",", ":"),
    ).encode("utf-8")
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def build_authorization_url(profile: OpenAPIProfile, state: str) -> str:
    """构造腾讯文档官方授权页 URL。"""
    return AUTHORIZE_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": profile.client_id,
            "redirect_uri": profile.redirect_uri,
            "new_login": "1",
            "response_type": "code",
            "scope": "all",
            "state": state,
        }
    )


class _CallbackState:
    def __init__(self, expected_state: str) -> None:
        self.expected_state = expected_state
        self.event = threading.Event()
        self.code = ""
        self.error = ""


def _handler_for(state: _CallbackState):
    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
            parsed = urllib.parse.urlparse(self.path)
            query = urllib.parse.parse_qs(parsed.query)
            received_state = (query.get("state") or [""])[0]
            if parsed.path != "/oauth/callback" or not secrets.compare_digest(
                received_state, state.expected_state
            ):
                self.send_response(400)
                body = "授权回调无效，请返回 AI 客户端重试。".encode("utf-8")
            else:
                state.code = (query.get("code") or [""])[0]
                state.error = (query.get("error_description") or query.get("error") or [""])[0]
                self.send_response(200)
                body = "腾讯文档授权已返回本机，可以关闭此页。".encode("utf-8")
                state.event.set()
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return CallbackHandler


def _exchange_code(
    profile: OpenAPIProfile,
    code: str,
    requester: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    url = TOKEN_URL + "?" + urllib.parse.urlencode(
        {
            "client_id": profile.client_id,
            "client_secret": profile.client_secret,
            "redirect_uri": profile.redirect_uri,
            "grant_type": "authorization_code",
            "code": code,
        }
    )
    try:
        if requester is not None:
            payload = requester(url)
        else:
            request = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise TencentDocsError("无法使用授权码换取腾讯文档 Token。") from exc
    if not isinstance(payload, dict):
        raise TencentDocsError("腾讯文档 Token 接口返回格式异常。")
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    open_id = str(payload.get("user_id") or "").strip()
    if not access_token or not refresh_token or not open_id:
        raise TencentDocsError("腾讯文档未返回完整的用户 Token。")
    return payload


def authorize_interactively(
    timeout: int = 300,
    *,
    browser_opener: Callable[[str], Any] = webbrowser.open,
    token_requester: Callable[..., Any] | None = None,
) -> dict[str, Any]:
    """打开官方授权页，接收 HTTPS 中转回调并保存 Token。"""
    profile = load_openapi_profile(required=True)
    assert profile is not None
    if not profile.app_configured:
        raise TencentDocsError("应用配置不完整，请重新运行 openapi_setup.py。")
    server = None
    for candidate_port in CALLBACK_PORTS:
        try:
            server = ThreadingHTTPServer(
                ("127.0.0.1", candidate_port), BaseHTTPRequestHandler
            )
            break
        except OSError:
            continue
    if server is None:
        raise TencentDocsError(
            "本机 OAuth 回调端口 49680-49689 均被占用，请关闭占用程序后重试。"
        )
    port = int(server.server_address[1])
    callback_state = _CallbackState(_encode_state(secrets.token_urlsafe(32), port))
    server.RequestHandlerClass = _handler_for(callback_state)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    authorization_url = build_authorization_url(profile, callback_state.expected_state)
    try:
        if browser_opener(authorization_url) is False:
            raise TencentDocsError("无法自动打开浏览器授权页。")
        if not callback_state.event.wait(timeout=max(10, timeout)):
            raise TencentDocsError("等待腾讯文档授权超时，请重试。")
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
    if callback_state.error:
        raise TencentDocsError("用户取消授权，或腾讯文档拒绝了授权请求。")
    if not callback_state.code:
        raise TencentDocsError("授权回调中没有一次性授权码。")
    payload = _exchange_code(profile, callback_state.code, token_requester)
    updated = replace(
        profile,
        open_id=str(payload["user_id"]),
        access_token=str(payload["access_token"]),
        refresh_token=str(payload["refresh_token"]),
        expires_at=int(time.time()) + int(payload.get("expires_in") or 0),
    )
    save_openapi_profile(updated)
    return {
        "authorized": True,
        "token_saved_to_system_keyring": True,
        "expires_at": updated.expires_at,
        "redirect_uri": updated.redirect_uri,
    }


def interactive_setup(login: bool = True) -> dict[str, Any]:
    """命令行首次配置，Client Secret 使用隐藏输入。"""
    client_id = input("Client ID: ").strip()
    client_secret = getpass.getpass("Client Secret（输入不显示）: ").strip()
    entered_redirect = input(f"HTTPS 回调地址 [{DEFAULT_REDIRECT_URI}]: ").strip()
    profile = configure_openapi_app(
        client_id,
        client_secret,
        entered_redirect or DEFAULT_REDIRECT_URI,
    )
    result: dict[str, Any] = {
        "configured": profile.app_configured,
        "redirect_uri": profile.redirect_uri,
    }
    if login:
        result.update(authorize_interactively())
    return result
