#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"

if [ ! -x "$PYTHON_BIN" ]; then
  echo "未找到项目虚拟环境，请先执行 ./install.sh" >&2
  exit 1
fi

exec "$PYTHON_BIN" "$SCRIPT_DIR/server.py"
