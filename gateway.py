"""兼容旧配置的启动入口；仅启动本项目的腾讯文档扩展工具。"""

from server import mcp


def main() -> None:
    """启动 stdio MCP 服务。"""
    mcp.run()


if __name__ == "__main__":
    main()
