"""兼容旧配置的启动入口；仅启动本项目的腾讯文档扩展工具。"""

from server import mcp


if __name__ == "__main__":
    mcp.run()
