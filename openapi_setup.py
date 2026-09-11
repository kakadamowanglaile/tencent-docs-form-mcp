"""首次配置用户自己的腾讯文档开放平台应用。"""

from __future__ import annotations

import argparse
import json
import sys

from openapi_auth import interactive_setup
from openapi_setup_ui import open_setup_ui
from tencent_form import TencentDocsError


def main() -> int:
    # 英文版 Windows 的默认控制台编码可能无法输出中文帮助。
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(
        description="保存你自己的腾讯文档应用配置，并完成 OAuth2 授权。"
    )
    parser.add_argument(
        "--terminal",
        action="store_true",
        help="使用终端问答，不打开本机设置页面。",
    )
    parser.add_argument(
        "--no-login",
        action="store_true",
        help="终端模式中只保存应用配置，稍后再授权。",
    )
    args = parser.parse_args()
    if args.no_login and not args.terminal:
        parser.error("--no-login 需要和 --terminal 一起使用")
    try:
        if args.terminal:
            result = interactive_setup(login=not args.no_login)
        else:
            result = open_setup_ui(block=True)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except TencentDocsError as exc:
        print(f"配置失败：{exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
