"""安全检查本机浏览器中的腾讯文档登录态，不输出 Cookie。"""

from __future__ import annotations

import argparse
import os
import sys

from tencent_form import SUPPORTED_BROWSERS, TencentDocsError, TencentFormClient, load_auth


def configure_console_encoding() -> None:
    """让旧版 Windows 控制台能够显示中文帮助和检查结果。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="检查腾讯文档收集表登录和所有者权限。")
    parser.add_argument("--form-url", required=True, help="腾讯文档原生收集表链接。")
    parser.add_argument(
        "--browser",
        choices=sorted(SUPPORTED_BROWSERS),
        default="firefox" if sys.platform == "win32" else "chrome",
        help="用于登录腾讯文档的浏览器。Windows 默认 Firefox，其他系统默认 Chrome。",
    )
    return parser.parse_args()


def main() -> int:
    configure_console_encoding()
    args = parse_args()
    os.environ["TENCENT_DOCS_USE_BROWSER_COOKIES"] = "1"
    os.environ["TENCENT_DOCS_BROWSER"] = args.browser
    try:
        auth = load_auth(required=True)
        data = TencentFormClient(auth).fetch_form(args.form_url, "head")["data"]
    except TencentDocsError as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1

    print(f"浏览器：{auth.source}")
    print(f"已登录：{'是' if data.get('isLogin') else '否'}")
    print(f"创建者：{'是' if data.get('isOwner') else '否'}")
    print(f"管理员：{'是' if data.get('isAdmin') else '否'}")
    print(f"可编辑：{'是' if (data.get('privilegeAttribute') or {}).get('can_edit') else '否'}")
    return 0 if data.get("isLogin") and (data.get("isOwner") or data.get("isAdmin")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
