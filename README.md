# 腾讯文档完整 MCP

[![跨平台测试](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/kakadamowanglaile/tencent-docs-form-mcp/actions/workflows/test.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

让 Codex、Claude、WorkBuddy、Cursor 等支持本地 `stdio MCP` 的 AI 客户端，通过同一个服务调用腾讯文档。后续文档操作不依赖浏览器点击自动化。

- 动态代理腾讯文档官方 MCP 的实时 `tools/list`；2026-09-11 实测为 224 个官方工具。
- 覆盖文档、表格、幻灯片、智能表、智能文档、流程图、OCR、导入导出、权限和文件管理。
- 新增 25 个正式 Open API 相关工具：21 项官方 MCP 未完整打包的能力，加上设置窗口、授权登录、退出和状态检查。
- 保留公开 API 仍未提供的收集表题目编辑等网页扩展能力。
- 当前统一服务暴露 265 个不重名工具；官方 MCP 后续新增工具时，总数会动态变化。
- 官方新增工具会在下次启动或缓存刷新后自动出现，不需要本项目重新发版。

> 这是社区项目，不是腾讯官方产品。项目会分别标记官方 MCP、正式 Open API 和网页内部接口。只有前两类属于腾讯公开能力；网页内部接口可能随腾讯改版失效。

## 支持的 AI 客户端

项目使用标准本地 `stdio MCP`，不绑定某一个 AI 产品。已经提供配置格式的客户端包括：

- Codex 桌面版和 Codex CLI
- Claude Desktop 和 Claude Code
- WorkBuddy
- Cursor、VS Code 等能够配置本地 stdio MCP 的客户端

AI 产品本身如果不支持 MCP，无法直接加载本项目。Claude.ai、ChatGPT 网页版等只接受远程 Connector 的场景，需要另行部署 Streamable HTTP 服务；当前仓库默认是更适合个人账号和本机凭据的 stdio 版本。

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
| 正式 Open API 25 个相关工具的协议、参数、端点和错误处理 | 已通过模拟官方响应测试 |
| 本机授权窗口打开、字段隐藏与安全限制 | 已实际浏览器检查并通过自动测试 |
| 标准 stdio 子进程启动、工具发现和调用 | 已测试；用于 Codex、Claude Code 等客户端 |
| 正式 Open API 调用真实腾讯账号 | 等待开放平台应用 OAuth2 凭据，尚未验证 |
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

## 正式 Open API 一键授权

官方 MCP Token 与正式 Open API OAuth2 Token 是两套凭据。每位用户使用自己在[腾讯文档开放平台](https://docs.qq.com/open/)创建并审核的应用，不共享仓库作者的账号或密钥。

首次使用：

1. 在开放平台应用中开通需要的权限并通过审核。

   - 读取文档分享权限：`scope.drive.file.permission.readonly` 或 `scope.drive.file.permission`
   - 读取文件夹操作权限：还可使用 `scope.drive.file.metadata`

2. 把下列 HTTPS 回调地址加入应用白名单：

```text
https://kakadamowanglaile.github.io/tencent-docs-form-mcp/
```

3. 双击项目根目录的 `授权腾讯文档.command`（macOS）或 `授权腾讯文档.bat`（Windows）。也可以在项目目录运行：

macOS / Linux：

```bash
.venv/bin/python openapi_setup.py
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe .\openapi_setup.py
```

程序会打开仅限本机访问的设置窗口。第一次粘贴自己的 Client ID 和 Client Secret，点击“保存并授权”；以后只显示一个“授权腾讯文档”按钮。Client Secret 保存到当前操作系统的密钥库。用户确认后，一次性授权码经静态 HTTPS 页面返回本机 `127.0.0.1:49680-49689` 的专用端口，本机换取并保存 Token。中转页不接收 Client Secret、Access Token 或 Refresh Token。

已经把 MCP 加到 AI 客户端时，也可以直接让 AI 调用 `tencent_docs_openapi_setup`。它会在用户电脑上打开同一个本机设置窗口，配置值不会作为 MCP 工具参数传给 AI。

正常的 Token 过期会自动使用 Refresh Token 更新；尚未授权或需要重新授权时，AI 可直接调用 `tencent_docs_openapi_login`。高级用户仍可使用 [`examples/openapi.env.example`](examples/openapi.env.example) 的环境变量方式。

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

## 添加到任意 MCP 客户端

核心配置只有两个值：Python 解释器路径和 `gateway.py` 的绝对路径。JSON 客户端可以使用下面的配置；WorkBuddy、Claude Desktop 以及采用 `mcpServers` 格式的客户端均可参考。

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

可复制的 JSON 和 TOML 模板位于 [`examples`](examples) 目录。不要整份覆盖客户端现有配置，只增加 `tencent-docs-complete` 这一项。推荐用 `openapi_setup.py` 把凭据保存到系统密钥库；环境变量模板仅供高级用户和 CI 使用。

### Codex

把对应示例中的内容加入 `~/.codex/config.toml`：

- macOS/Linux：[`mcp-config.codex.macos.example.toml`](examples/mcp-config.codex.macos.example.toml)
- Windows：[`mcp-config.codex.windows.example.toml`](examples/mcp-config.codex.windows.example.toml)

### Claude Code

Claude Code 可以把同样的 stdio 配置加入用户级 MCP：

```bash
claude mcp add-json --scope user tencent-docs-complete '{"type":"stdio","command":"/ABSOLUTE/PATH/tencent-docs-form-mcp/.venv/bin/python","args":["/ABSOLUTE/PATH/tencent-docs-form-mcp/gateway.py"],"env":{"TENCENT_DOCS_USE_BROWSER_COOKIES":"1","TENCENT_DOCS_BROWSER":"chrome"}}'
```

Windows PowerShell 可以直接使用 [`mcp-config.windows.example.json`](examples/mcp-config.windows.example.json) 中的服务器对象，通过 `claude mcp add-json` 添加。Claude Desktop 可在本地 MCP 或扩展开发配置中使用同一对象。

### WorkBuddy 和其他 JSON 客户端

使用 [`mcp-config.macos.example.json`](examples/mcp-config.macos.example.json) 或 [`mcp-config.windows.example.json`](examples/mcp-config.windows.example.json)。保存并重启客户端后，可以这样说：

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

正式 Open API 工具：

- `tencent_docs_openapi_status`：检查配置，也可实际校验 Access Token；不返回任何凭据值。
- `tencent_docs_openapi_setup`：打开本机设置窗口；首次填写应用信息，以后只需点击授权。
- `tencent_docs_openapi_login`：打开腾讯官方授权页，自动接收回调、换 Token 并保存到系统密钥库。
- `tencent_docs_openapi_logout`：删除本机用户 Token，保留用户自己的应用配置。
- `tencent_docs_openapi_set_starred`、`tencent_docs_openapi_set_pinned`：收藏和置顶。
- `tencent_docs_openapi_set_watermark`：设置文字水印和访客水印。
- `tencent_docs_openapi_create_shortcut`、`tencent_docs_openapi_recover_file`：快捷方式和回收站恢复。
- `tencent_docs_openapi_get_user_access`：读取当前用户的详细访问能力。
- `tencent_docs_openapi_get_file_permission`：读取完整分享策略、复制和批注开关。
- `tencent_docs_openapi_get_folder_permission`：读取用户对文件夹的查看、编辑、分享和添加成员能力。
- `tencent_docs_openapi_transfer_ownership`：转让所有权，要求精确确认词。
- `tencent_docs_openapi_set_file_permission`：设置分享策略、复制下载打印和只读批注开关。
- `tencent_docs_openapi_apply_file_permission`：申请查看或编辑权限。
- `tencent_docs_openapi_add_collaborators`、`tencent_docs_openapi_remove_collaborator`、`tencent_docs_openapi_list_collaborators`：协作成员管理。
- `tencent_docs_openapi_filter_files`：按目录、类型、所有者和排序条件读取文件。
- `tencent_docs_openapi_convert_file_id`：在 fileID 与 encodedID 之间转换。
- `tencent_docs_openapi_get_usage`、`tencent_docs_openapi_get_unread_count`：应用使用量与未读消息。
- `tencent_docs_openapi_set_form_release`：发布、暂停或设置收集截止时间。
- `tencent_docs_openapi_generate_form_result`：生成收集结果表格。
- `tencent_docs_openapi_batch_insert_sheet_images`：一次插入最多 500 张表格图片。

调用示例见 [`docs/OpenAPI使用示例.md`](docs/OpenAPI使用示例.md)，工具来源和实测边界见 [`docs/能力矩阵.md`](docs/能力矩阵.md)。

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
