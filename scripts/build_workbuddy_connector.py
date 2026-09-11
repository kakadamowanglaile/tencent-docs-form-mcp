"""生成 WorkBuddy 开放平台可上传的连接器 ZIP。"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "workbuddy-connector"
REQUIRED = (
    "connector-meta.json",
    "cli.json",
    "icon.svg",
    "skills/tencent-docs-extensions/SKILL.md",
)
MAX_BYTES = 20 * 1024 * 1024
FORBIDDEN = ("TENCENT_DOCS_COOKIE=", "Access-Token:", "Client Secret:")


def validate_source() -> None:
    for relative in REQUIRED:
        if not (SOURCE / relative).is_file():
            raise ValueError(f"缺少必需文件：{relative}")
    meta = json.loads((SOURCE / "connector-meta.json").read_text("utf-8"))
    config = json.loads((SOURCE / "cli.json").read_text("utf-8"))
    if meta.get("type") != "cli":
        raise ValueError("connector-meta.json 的 type 必须是 cli。")
    if (config.get("runtime") or {}).get("type") != "python":
        raise ValueError("cli.json 必须声明 Python 运行时。")
    for path in SOURCE.rglob("*"):
        if not path.is_file():
            continue
        text = path.read_text("utf-8")
        for secret in FORBIDDEN:
            if secret in text:
                raise ValueError(f"文件疑似包含凭证：{path.relative_to(SOURCE)}")


def build(output: Path) -> None:
    validate_source()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(SOURCE.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(SOURCE).as_posix())
    if output.stat().st_size > MAX_BYTES:
        output.unlink()
        raise ValueError("ZIP 超过 WorkBuddy 的 20 MB 限制。")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "dist" / "tencent-docs-extensions-workbuddy-0.8.0.zip",
    )
    args = parser.parse_args()
    try:
        build(args.output.resolve())
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"生成失败：{exc}", file=sys.stderr)
        return 1
    print(args.output.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
