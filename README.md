# 腾讯文档原生收集表 MCP

[![跨平台测试](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

让 WorkBuddy 等 MCP 客户端直接读取、编辑和发布腾讯文档原生收集表，不依赖浏览器点击自动化。

支持问答题、单选题、多选题和下拉选择。写入后会回读草稿核对，发布后会使用不带登录 Cookie 的请求检查公开版本。

> 这是社区项目，不是腾讯官方产品。题目保存和表单设置使用腾讯文档网页当前采用的未公开接口；腾讯改版后可能失效。

## 验证情况

| 环境或能力 | 状态 |
| --- | --- |
| macOS + Chrome 登录、写入、发布 | 已实际验证 |
| 不带 Cookie 读取公开表单 | 已实际验证 |
| Windows 安装、导入、MCP 工具协议 | 由 GitHub Actions 验证 |
| Windows 读取腾讯文档真实登录态 | 尚未在 Windows 真机验证 |
| 访客免登录提交 | 不保证；腾讯文档权限策略可能要求登录 |

## 安装

需要 Python 3.10 或更高版本，并先在浏览器中登录 [腾讯文档](https://docs.qq.com)。

### macOS / Linux

```bash
git clone https://github.com/kakadamowanglaile/tencent-docs-form-mcp.git
cd tencent-docs-form-mcp
chmod +x install.sh run-mcp.sh
./install.sh
```

### Windows

在 PowerShell 中执行：

```powershell
git clone https://github.com/kakadamowanglaile/tencent-docs-form-mcp.git
cd tencent-docs-form-mcp
powershell -ExecutionPolicy Bypass -File .\install-windows.ps1
```

Windows 建议使用 Firefox 登录腾讯文档。新版 Chrome/Edge 的 Cookie 可能受 Windows 加密策略限制，第三方进程无法解密。

## 检查登录态

把链接换成你自己创建的腾讯文档原生收集表。

macOS：

```bash
.venv/bin/python auth_check.py \
  --form-url "https://docs.qq.com/form/page/你的表单TOKEN" \
  --browser chrome
```

Windows：

```powershell
.\.venv\Scripts\python.exe .\auth_check.py `
  --form-url "https://docs.qq.com/form/page/你的表单TOKEN" `
  --browser firefox
```

该命令只显示登录和编辑权限状态，不输出 Cookie。

## 添加到 WorkBuddy

打开 WorkBuddy 的“设置 → MCP → 添加 MCP Server”，新增一个 stdio MCP。不要把整份示例文件覆盖到已有配置中，只添加 `tencent-docs-form` 这一项。

macOS 示例：

```json
{
  "mcpServers": {
    "tencent-docs-form": {
      "command": "/你的路径/tencent-docs-form-mcp/.venv/bin/python",
      "args": [
        "/你的路径/tencent-docs-form-mcp/server.py"
      ],
      "env": {
        "TENCENT_DOCS_USE_BROWSER_COOKIES": "1",
        "TENCENT_DOCS_BROWSER": "chrome"
      }
    }
  }
}
```

Windows 示例：

```json
{
  "mcpServers": {
    "tencent-docs-form": {
      "command": "C:\\你的路径\\tencent-docs-form-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\你的路径\\tencent-docs-form-mcp\\server.py"
      ],
      "env": {
        "TENCENT_DOCS_USE_BROWSER_COOKIES": "1",
        "TENCENT_DOCS_BROWSER": "firefox"
      }
    }
  }
}
```

可直接复制的配置模板位于 [`examples`](examples) 目录。保存配置并重启 WorkBuddy 后，可以这样说：

> 检查这个腾讯文档收集表，然后把题目改成姓名、手机号、报名项目三个问题，确认后发布。表单链接是……

## MCP 工具

- `tencent_docs_inspect_form`：读取题目、发布状态和当前账号权限，不修改内容。
- `tencent_docs_replace_form_questions`：完整替换题目但不发布。
- `tencent_docs_publish_form`：发布现有草稿，并检查公开版本。
- `tencent_docs_build_and_publish_form`：替换题目、设置匿名选项、发布并检查公开版本。

写入工具会完整替换现有题目。使用前建议先复制一份表单进行测试。

## 登录方式

MCP 默认不会扫描浏览器数据。只有配置以下环境变量后才会读取 `docs.qq.com` 的 Cookie：

```text
TENCENT_DOCS_USE_BROWSER_COOKIES=1
TENCENT_DOCS_BROWSER=chrome
```

`TENCENT_DOCS_BROWSER` 支持 `brave`、`chrome`、`chromium`、`edge`、`firefox`、`vivaldi`。

也支持通过进程环境变量 `TENCENT_DOCS_COOKIE` 提供 Cookie header，但不要把 Cookie 写进仓库、配置示例或聊天消息。

## 作为 Skill 使用

[`SKILL.md`](SKILL.md) 提供了 Agent 的调用规则。MCP 负责真正连接腾讯文档；Skill 只告诉 AI 应该何时调用哪个工具、如何检查结果。因此只复制 Skill、没有启动 MCP，不能编辑腾讯文档。

## 开发与测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub Actions 会在 Ubuntu、macOS、Windows，以及 Python 3.10 和 3.13 上执行测试。跨平台测试不包含真实腾讯账号，Windows 的真实浏览器登录仍需要用户本机检查。

## 安全说明

- Cookie 只保留在 MCP 进程内存中，不会写入项目文件或工具返回值。
- 仅表单创建者或管理员可以写入和发布。
- 项目不会绕过腾讯文档登录、访问权限或提交限制。
- 安全问题请参阅 [`SECURITY.md`](SECURITY.md)。

## 许可证

[MIT](LICENSE)
