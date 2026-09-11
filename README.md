# 腾讯文档完整 MCP

[![跨平台测试](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

让 WorkBuddy 等 MCP 客户端通过一个本地 MCP 使用腾讯文档的官方能力和网页扩展能力，后续操作不依赖浏览器点击自动化。

- 动态代理腾讯文档官方 MCP 的实时 `tools/list`；2026-09-11 实测为 224 个官方工具。
- 覆盖文档、表格、幻灯片、智能表、智能文档、流程图、OCR、导入导出、权限和文件管理。
- 补充官方 MCP 尚未打包的收集表题目编辑、发布、收藏、回收站恢复、快捷方式和置顶等功能。
- 官方新增工具会在下次启动或缓存刷新后自动出现，不需要本项目重新发版。

> 这是社区项目，不是腾讯官方产品。官方能力转发到 [腾讯文档官方 MCP](https://docs.qq.com/openapi/mcp)；扩展能力使用腾讯文档网页当前采用的未公开接口，腾讯改版后可能失效。“完整”指官方工具全量代理加已实现扩展，不代表腾讯网页的每一个内部接口都属于稳定 API。

## 验证情况

| 环境或能力 | 状态 |
| --- | --- |
| macOS + Chrome 登录、写入、发布 | 已实际验证 |
| 不带 Cookie 读取公开表单 | 已实际验证 |
| Windows 安装、导入、MCP 工具协议 | 由 GitHub Actions 验证 |
| Windows 自动打开登录、加密保存登录态、自动关窗 | 已在 Windows 11 真机验证 |
| Windows 通过登录态新建、写入、发布、公开回读 | 已在 Windows 11 真机验证 |
| macOS 自动获取官方 Token、动态读取 224 个工具 | 已实际验证 |
| 官方工具经本地统一 MCP 转发 | 已实际调用验证 |
| 最近/根目录/收藏/共享/回收站列表 | 已实际验证 |
| 收藏、回收站恢复、快捷方式、置顶 | 已用临时文件验证 |
| Windows 保存的登录态自动连接官方 MCP | 已实现，尚未在 Windows 真机验证 |
| 云盘版本历史 | 已实现实验工具；在线文档/收集表返回 `unsupported ext` |
| 永久删除、清空回收站 | 已实现且要求精确确认词；未做真实不可恢复测试 |
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

安装完成后运行一次登录助手：

```powershell
.\.venv\Scripts\python.exe .\browser_login.py
```

它会自动寻找 Chrome、Edge、Brave、Vivaldi 或 Chromium，打开腾讯文档登录页。你登录成功后窗口会立即自动关闭，并由 Windows 使用当前系统账号加密保存登录状态。没有 Chrome 时会自动使用 Edge，不需要你预先新建表单。

如果不想让本地 MCP 从登录态获取官方 Token，也可以在 [腾讯文档 MCP Token 页](https://docs.qq.com/open/auth/mcp.html) 生成 Token，然后只在本机 MCP 环境中设置 `TENCENT_DOCS_MCP_TOKEN`。不要把 Token 提交到 GitHub。

## 检查登录态

把链接换成你自己创建的腾讯文档原生收集表。

macOS：

```bash
.venv/bin/python auth_check.py \
  --form-url "https://docs.qq.com/form/page/你的表单TOKEN" \
  --browser chrome
```

Windows 登录后不必提供已有表单；可以让 MCP 直接新建。若要检查某个已有表单，可运行：

```powershell
$env:TENCENT_DOCS_USE_SAVED_LOGIN = "1"
.\.venv\Scripts\python.exe .\auth_check.py `
  --form-url "https://docs.qq.com/form/page/你的表单TOKEN" `
  --saved-login
```

该命令只显示登录和编辑权限状态，不输出 Cookie。

## 添加到 WorkBuddy

打开 WorkBuddy 的“设置 → MCP → 添加 MCP Server”，新增一个 stdio MCP。不要把整份示例文件覆盖到已有配置中，只添加 `tencent-docs-complete` 这一项。

macOS 示例：

```json
{
  "mcpServers": {
    "tencent-docs-complete": {
      "command": "/你的路径/tencent-docs-form-mcp/.venv/bin/python",
      "args": [
        "/你的路径/tencent-docs-form-mcp/gateway.py"
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
    "tencent-docs-complete": {
      "command": "C:\\你的路径\\tencent-docs-form-mcp\\.venv\\Scripts\\python.exe",
      "args": [
        "C:\\你的路径\\tencent-docs-form-mcp\\gateway.py"
      ],
      "env": {
        "TENCENT_DOCS_USE_SAVED_LOGIN": "1"
      }
    }
  }
}
```

可直接复制的配置模板位于 [`examples`](examples) 目录。保存配置并重启 WorkBuddy 后，可以这样说：

0.1.x 用户升级时，需要把 MCP 配置中的启动文件从 `server.py` 改为 `gateway.py`；`server.py` 仅保留本项目扩展工具。

> 检查这个腾讯文档收集表，然后把题目改成姓名、手机号、报名项目三个问题，确认后发布。表单链接是……

## MCP 工具

官方工具不在项目中写死。`gateway.py` 会读取官方 `tools/list` 的名称、说明和参数 Schema，并原样转发调用。实际工具数以 `tencent_docs_official_status` 为准。

本项目的扩展工具：

- `tencent_docs_login`：Windows 上自动弹出可用浏览器，登录成功后立即关窗并加密保存登录状态。
- `tencent_docs_official_status`：检查官方 MCP 授权和当前工具数，不返回 Token。
- `tencent_docs_inspect_form`：读取题目、发布状态和当前账号权限，不修改内容。
- `tencent_docs_create_form`：使用当前登录账号新建一份空白收集表。
- `tencent_docs_replace_form_questions`：完整替换题目但不发布。
- `tencent_docs_publish_form`：发布现有草稿，并检查公开版本。
- `tencent_docs_build_and_publish_form`：替换题目、设置匿名选项、发布并检查公开版本。
- `tencent_docs_create_and_publish_form`：新建收集表、写入题目、发布并检查公开版本，不需要预先提供表单链接。
- `tencent_docs_list_files`：读取最近、收藏、与我共享、回收站或文件夹列表。
- `tencent_docs_set_starred`：收藏或取消收藏。
- `tencent_docs_restore_file`：从回收站恢复文件。
- `tencent_docs_add_shortcut`：在指定文件夹创建文件快捷方式。
- `tencent_docs_set_pinned`：置顶或取消置顶。
- `tencent_docs_list_versions`：实验性的云盘文件版本查看，不适用于腾讯在线文档。
- `tencent_docs_permanently_delete_trash_item`：永久删除单个回收站项目，必须精确提供确认词。
- `tencent_docs_clear_trash`：永久清空回收站，必须精确提供确认词。

写入工具会完整替换现有题目。使用前建议先复制一份表单进行测试。

## 登录方式

Windows 推荐使用 `browser_login.py`。浏览器只负责让你本人登录；登录完成后会自动关闭，后续创建、编辑、发布全部直接调用接口，不会操控浏览器。登录状态保存在 `%LOCALAPPDATA%\TencentDocsFormMCP\auth.bin`，内容受 Windows 当前账号加密保护。

Windows MCP 配置：

```text
TENCENT_DOCS_USE_SAVED_LOGIN=1
```

其他系统仍可显式选择浏览器 Cookie：

```text
TENCENT_DOCS_USE_BROWSER_COOKIES=1
TENCENT_DOCS_BROWSER=chrome
```

`TENCENT_DOCS_BROWSER` 支持 `brave`、`chrome`、`chromium`、`edge`、`firefox`、`vivaldi`。这条旧方式读取浏览器自身的 Cookie；Windows 新登录助手不会受新版 Chrome/Edge Cookie 加密方式影响。

也支持通过进程环境变量 `TENCENT_DOCS_COOKIE` 提供 Cookie header，但不要把 Cookie 写进仓库、配置示例或聊天消息。

## 作为 Skill 使用

[`SKILL.md`](SKILL.md) 提供了 Agent 的调用规则。MCP 负责真正连接腾讯文档；Skill 只告诉 AI 应该何时调用哪个工具、如何检查结果。因此只复制 Skill、没有启动 MCP，不能编辑腾讯文档。

## 开发与测试

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

GitHub Actions 会在 Ubuntu、macOS、Windows，以及 Python 3.10 和 3.13 上执行测试。自动测试不包含真实腾讯账号。详细范围见 [`docs/能力矩阵.md`](docs/能力矩阵.md)。

## 安全说明

- Windows 登录助手将 Cookie 写入当前账号才能解密的系统加密文件，不会写入项目或工具返回值。
- 官方 MCP Token 只保存在 MCP 进程内存或用户自己的本机环境中。
- 仅表单创建者或管理员可以写入和发布。
- 项目不会绕过腾讯文档登录、访问权限或提交限制。
- 安全问题请参阅 [`SECURITY.md`](SECURITY.md)。

## 许可证

[MIT](LICENSE)
