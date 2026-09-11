"""腾讯文档原生收集表客户端。

这个客户端调用腾讯文档网页自身使用的内部接口，不使用浏览器自动化。
登录态只从环境变量或用户明确指定的本机浏览器 Cookie 库读入，
不会写入文件、日志或工具返回值。
"""

from __future__ import annotations

import json
import os
import platform
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import Cookie, CookieJar
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any, Literal


BASE_URL = "https://docs.qq.com"
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
)
SUCCESS_RETCODE = 0
QuestionType = Literal["SIMPLE", "RADIO", "CHECKBOX", "SELECT"]
SUPPORTED_BROWSERS = {
    "brave": "brave",
    "chrome": "chrome",
    "chromium": "chromium",
    "edge": "edge",
    "firefox": "firefox",
    "vivaldi": "vivaldi",
}


class TencentDocsError(RuntimeError):
    """可向 AI 和用户展示的腾讯文档错误。"""


@dataclass(frozen=True)
class FormAddress:
    """收集表公开链接中的地址信息。"""

    url: str
    token: str


@dataclass
class AuthContext:
    """仅在进程内存中保留的登录上下文。"""

    cookie_jar: CookieJar
    xsrf: str
    source: str


def parse_form_url(form_url: str) -> FormAddress:
    """验证并解析腾讯文档原生收集表链接。"""
    parsed = urllib.parse.urlparse(form_url.strip())
    if parsed.scheme != "https" or parsed.hostname != "docs.qq.com":
        raise TencentDocsError("仅支持 https://docs.qq.com 的收集表链接。")
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) < 3 or parts[0] != "form" or parts[1] != "page":
        raise TencentDocsError("链接不是腾讯文档原生收集表页面。")
    token = parts[2]
    if not token or len(token) > 200:
        raise TencentDocsError("收集表链接中的 token 无效。")
    normalized = urllib.parse.urlunparse(
        ("https", "docs.qq.com", f"/form/page/{token}", "", parsed.query, "")
    )
    return FormAddress(url=normalized, token=token)


def _cookie_from_pair(name: str, value: str) -> Cookie:
    return Cookie(
        version=0,
        name=name,
        value=value,
        port=None,
        port_specified=False,
        domain=".docs.qq.com",
        domain_specified=True,
        domain_initial_dot=True,
        path="/",
        path_specified=True,
        secure=True,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest={"HttpOnly": None},
        rfc2109=False,
    )


def _load_raw_cookie(raw_cookie: str) -> AuthContext:
    parsed = SimpleCookie()
    parsed.load(raw_cookie)
    jar = CookieJar()
    for morsel in parsed.values():
        jar.set_cookie(_cookie_from_pair(morsel.key, morsel.value))
    xsrf = next((cookie.value for cookie in jar if cookie.name == "TOK"), "")
    if not xsrf:
        raise TencentDocsError("登录 Cookie 中缺少 TOK，无法执行写入操作。")
    return AuthContext(cookie_jar=jar, xsrf=xsrf, source="environment")


def _load_browser_cookies(browser_name: str) -> AuthContext:
    try:
        import browser_cookie3
    except ImportError as exc:
        raise TencentDocsError(
            "缺少 browser-cookie3，请先执行本项目的安装脚本。"
        ) from exc

    normalized_name = browser_name.strip().lower()
    loader_name = SUPPORTED_BROWSERS.get(normalized_name)
    if loader_name is None:
        supported = "、".join(sorted(SUPPORTED_BROWSERS))
        raise TencentDocsError(f"不支持浏览器 {browser_name!r}，可选：{supported}。")
    loader = getattr(browser_cookie3, loader_name, None)
    if not callable(loader):
        raise TencentDocsError(f"browser-cookie3 不支持 {normalized_name}。")

    cookie_file = os.environ.get("TENCENT_DOCS_BROWSER_COOKIE_FILE", "").strip()
    if not cookie_file and normalized_name == "chrome":
        cookie_file = os.environ.get("TENCENT_DOCS_CHROME_COOKIE_FILE", "").strip()
    kwargs: dict[str, Any] = {"domain_name": "docs.qq.com"}
    if cookie_file:
        resolved = Path(cookie_file).expanduser().resolve()
        if not resolved.is_file():
            raise TencentDocsError("指定的浏览器 Cookie 文件不存在。")
        kwargs["cookie_file"] = str(resolved)
    try:
        jar = loader(**kwargs)
    except Exception as exc:
        operating_system = platform.system() or "当前系统"
        raise TencentDocsError(
            f"无法在 {operating_system} 读取 {normalized_name} 中 docs.qq.com 的登录态。"
            "请确认该浏览器已登录腾讯文档，并允许系统凭据库访问。"
            "Windows 的新版 Chrome/Edge 如果解密失败，请改用 Firefox。"
        ) from exc
    xsrf = next((cookie.value for cookie in jar if cookie.name == "TOK"), "")
    if not xsrf:
        raise TencentDocsError(
            f"{normalized_name} 中没有找到有效的腾讯文档 TOK Cookie，"
            "请重新登录 docs.qq.com。"
        )
    return AuthContext(cookie_jar=jar, xsrf=xsrf, source=normalized_name)


def load_auth(required: bool = False) -> AuthContext | None:
    """根据显式配置读取登录态，不会默认扫描浏览器 Cookie。"""
    raw_cookie = os.environ.get("TENCENT_DOCS_COOKIE", "").strip()
    if raw_cookie:
        return _load_raw_cookie(raw_cookie)
    browser_opt_in = os.environ.get("TENCENT_DOCS_USE_BROWSER_COOKIES", "") == "1"
    legacy_chrome_opt_in = os.environ.get("TENCENT_DOCS_USE_CHROME_COOKIES", "") == "1"
    if browser_opt_in or legacy_chrome_opt_in:
        browser_name = os.environ.get("TENCENT_DOCS_BROWSER", "chrome")
        return _load_browser_cookies(browser_name)
    if required:
        raise TencentDocsError(
            "写入和发布需要登录态。请设置 TENCENT_DOCS_USE_BROWSER_COOKIES=1 "
            "并用 TENCENT_DOCS_BROWSER 选择浏览器，"
            "或在本机进程环境中设置 TENCENT_DOCS_COOKIE。"
        )
    return None


class TencentFormClient:
    """腾讯文档原生收集表 HTTP 客户端。"""

    def __init__(self, auth: AuthContext | None = None, timeout: float = 30.0):
        self.auth = auth
        self.timeout = timeout
        handlers: list[Any] = []
        if auth is not None:
            handlers.append(urllib.request.HTTPCookieProcessor(auth.cookie_jar))
        self.opener = urllib.request.build_opener(*handlers)

    def _request_json(
        self,
        path: str,
        *,
        method: str = "GET",
        params: dict[str, Any] | None = None,
        body: dict[str, Any] | list[Any] | None = None,
        referer: str = BASE_URL + "/",
    ) -> dict[str, Any]:
        query = dict(params or {})
        if self.auth is not None and self.auth.xsrf:
            query.setdefault("xsrf", self.auth.xsrf)
        url = BASE_URL + path
        if query:
            url += "?" + urllib.parse.urlencode(query)
        data = None
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Origin": BASE_URL,
            "Referer": referer,
            "User-Agent": USER_AGENT,
            "X-Requested-With": "XMLHttpRequest",
        }
        if body is not None:
            data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        payload = ""
        last_network_error: urllib.error.URLError | None = None
        for attempt in range(3):
            try:
                with self.opener.open(request, timeout=self.timeout) as response:
                    payload = response.read().decode("utf-8")
                last_network_error = None
                break
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403}:
                    raise TencentDocsError("腾讯文档拒绝了请求，请检查登录态和表单权限。") from exc
                raise TencentDocsError(f"腾讯文档请求失败，HTTP {exc.code}。") from exc
            except urllib.error.URLError as exc:
                last_network_error = exc
                if attempt < 2:
                    time.sleep(0.5 * (attempt + 1))
        if last_network_error is not None:
            raise TencentDocsError("连续 3 次无法连接腾讯文档，请检查网络。") from last_network_error
        try:
            result = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise TencentDocsError("腾讯文档返回了无法解析的数据。") from exc
        if not isinstance(result, dict):
            raise TencentDocsError("腾讯文档返回的数据结构异常。")
        return result

    @staticmethod
    def _ensure_success(result: dict[str, Any], action: str) -> dict[str, Any]:
        retcode = result.get("retcode")
        if retcode != SUCCESS_RETCODE:
            message = result.get("msg") or result.get("message") or "未提供错误说明"
            raise TencentDocsError(f"{action}失败，retcode={retcode}，{message}。")
        return result

    def fetch_form(self, form_url: str, tag: Literal["head", "pub"] = "head") -> dict[str, Any]:
        """读取收集表草稿或已发布版本。"""
        address = parse_form_url(form_url)
        result = self._request_json(
            "/form/data/get",
            params={"id": address.token, "normal": 1, "tag": tag},
            referer=address.url,
        )
        return self._ensure_success(result, "读取收集表")

    @staticmethod
    def decode_form_data(server_data: dict[str, Any]) -> dict[str, Any]:
        attributed = server_data.get("initialAttributedText") or {}
        raw = attributed.get("text", "{}")
        if not isinstance(raw, str):
            raise TencentDocsError("收集表文本格式异常。")
        try:
            decoded = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise TencentDocsError(
                "当前表单数据使用了工具尚未支持的编码格式。"
            ) from exc
        if not isinstance(decoded, dict):
            raise TencentDocsError("收集表内容不是对象结构。")
        return decoded

    @staticmethod
    def _require_owner(server_data: dict[str, Any]) -> None:
        privilege = server_data.get("privilegeAttribute") or {}
        if not server_data.get("isLogin"):
            raise TencentDocsError("当前未登录腾讯文档，已拒绝写入。")
        if not (server_data.get("isOwner") or server_data.get("isAdmin")):
            raise TencentDocsError("当前账号不是该收集表的创建者或管理员。")
        if not privilege.get("can_edit", False):
            raise TencentDocsError("当前账号没有编辑该收集表的权限。")

    def replace_form(self, form_url: str, form_data: dict[str, Any]) -> dict[str, Any]:
        """用完整文本替换收集表草稿。"""
        current = self.fetch_form(form_url, "head")["data"]
        self._require_owner(current)
        global_id = current.get("globalPadId")
        if not global_id:
            raise TencentDocsError("腾讯文档未返回 globalPadId。")
        payload = dict(form_data)
        payload["globalPadId"] = global_id
        payload["padId"] = current.get("localPadId", payload.get("padId", ""))
        result = self._request_json(
            "/form/data/post",
            method="POST",
            params={
                "padId": global_id,
                "rev": current.get("rev"),
                "pos": current.get("pos"),
                "fullText": 1,
            },
            body=payload,
            referer=parse_form_url(form_url).url + "#/edit",
        )
        return self._ensure_success(result, "保存收集表")

    def read_settings(self, form_url: str) -> dict[str, Any]:
        """读取收集表设置。"""
        current = self.fetch_form(form_url, "head")["data"]
        self._require_owner(current)
        result = self._request_json(
            "/api/form/read/settings",
            method="POST",
            body={
                "form_id": current["globalPadId"],
                "need_sync_cfg": False,
                "need_cycle_cfg": False,
                "need_statistics_cfg": False,
            },
            referer=parse_form_url(form_url).url + "#/setting",
        )
        return self._ensure_success(result, "读取收表设置")

    def set_anonymous(self, form_url: str, anonymous: bool) -> dict[str, Any]:
        """设置是否允许匿名提交；这不等同于免登录填写。"""
        current = self.fetch_form(form_url, "head")["data"]
        self._require_owner(current)
        result = self._request_json(
            "/api/form/write/settings",
            method="POST",
            body={"form_id": current["globalPadId"], "collect_cfg": {"anonymous": anonymous}},
            referer=parse_form_url(form_url).url + "#/setting",
        )
        return self._ensure_success(result, "更新匿名设置")

    def publish(self, form_url: str) -> dict[str, Any]:
        """立即发布收集表，不设截止时间。"""
        current = self.fetch_form(form_url, "head")["data"]
        self._require_owner(current)
        result = self._request_json(
            "/api/form/write/publish",
            method="POST",
            body={
                "form_id": current["globalPadId"],
                "end_time": 0,
                "start_time": 0,
                "form_type": 0,
            },
            referer=parse_form_url(form_url).url + "#/edit",
        )
        return self._ensure_success(result, "发布收集表")


def build_form_data(spec: dict[str, Any], server_data: dict[str, Any]) -> dict[str, Any]:
    """将简洁规格转换为腾讯文档原生收集表结构。"""
    now = int(time.time() * 1000)
    questions: list[dict[str, Any]] = []
    qlist: list[str] = []
    for index, item in enumerate(spec["questions"], start=1):
        question_id = f"question-{now}-{index}"
        question_type: QuestionType = item["type"]
        question: dict[str, Any] = {
            "id": question_id,
            "section": 0,
            "title": item["title"],
            "subtitle": item.get("subtitle", ""),
            "placeholder": "输入问题",
            "isDirty": False,
            "createTime": now,
            "updateTime": now,
            "type": question_type,
            "dataType": 1,
            "toggle": {
                "required": bool(item.get("required", False)),
                "randomOption": False,
                "showValidate": False,
                "showSubtitle": bool(item.get("subtitle")),
            },
        }
        if question_type == "SIMPLE":
            question["qdata"] = {"placeholder": item.get("placeholder") or "请填写"}
            question["validate"] = [
                {
                    "type": 12,
                    "rules": {"max": 500, "open": False},
                    "message": "输入内容需不超过500个字符。",
                }
            ]
            question["questionDescripe"] = {
                "simpleFirstIndex": 0,
                "simpleSecondIndex": 0,
                "simpleUserInputContent": "",
                "simpleUserInputContentSupply": "",
                "simpleUserInputErrorMessage": "",
            }
        else:
            options = item.get("options") or []
            qdata: dict[str, Any] = {
                "options": [
                    {"id": option_index, "title": title}
                    for option_index, title in enumerate(options, start=1)
                ]
            }
            if question_type == "SELECT":
                qdata["placeholder"] = item.get("placeholder") or "请选择"
            question["qdata"] = qdata
            question["validate"] = None
        questions.append(question)
        qlist.append(question_id)

    title = spec["title"]
    return {
        "formName": title,
        "updateTime": now,
        "title": title,
        "subtitle": spec.get("subtitle", ""),
        "author": "",
        "themeClass": "default",
        "padId": server_data.get("localPadId", ""),
        "globalPadId": server_data.get("globalPadId", ""),
        "isDirty": False,
        "rightBarClicked": False,
        "questions": questions,
        "sections": [{"sid": 0, "title": "", "qlist": qlist}],
    }


def summarize_form(result: dict[str, Any], auth_source: str = "none") -> dict[str, Any]:
    """生成不含凭证和个人标识的表单摘要。"""
    data = result["data"]
    form_data = TencentFormClient.decode_form_data(data)
    questions = form_data.get("questions") or []
    return {
        "title": form_data.get("title") or data.get("title") or "",
        "published": bool(data.get("pub")),
        "revision": data.get("rev"),
        "question_count": len(questions),
        "questions": [
            {
                "title": question.get("title", ""),
                "type": question.get("type", ""),
                "required": bool((question.get("toggle") or {}).get("required")),
            }
            for question in questions
        ],
        "is_login": bool(data.get("isLogin")),
        "is_owner": bool(data.get("isOwner")),
        "is_admin": bool(data.get("isAdmin")),
        "public_policy": data.get("policy"),
        "auth_source": auth_source,
    }


def compare_spec(spec: dict[str, Any], summary: dict[str, Any]) -> bool:
    """检查标题和题型是否与规格一致。"""
    expected = [(item["title"], item["type"]) for item in spec["questions"]]
    actual = [(item["title"], item["type"]) for item in summary["questions"]]
    return summary["title"] == spec["title"] and actual == expected
