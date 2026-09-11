---
name: tencent-docs-extensions
description: 通过社区版 CLI 使用腾讯文档官方连接器未打包的收集表、权限、协作者、文件操作和批量插图功能。
---

# 腾讯文档扩展工具（社区版）

这是社区项目，不是腾讯官方连接器。普通文档、表格、幻灯片编辑应使用官方腾讯文档连接器；只在需要以下扩展能力时使用本 CLI。

## 调用方式

先读取当前版本的工具名和 JSON Schema：

```bash
tencent-docs-extension tools --json
```

调用工具时必须传 JSON 对象，并优先设置 `response_format` 为 `json`：

```bash
tencent-docs-extension call tencent_docs_inspect_form --json '{"form_url":"https://docs.qq.com/form/page/EXAMPLE","response_format":"json"}'
```

在 Windows PowerShell 中使用单引号包住 JSON；如果当前 Shell 不支持单引号，按该 Shell 规则转义双引号。

## 核心能力

- 原生收集表：`tencent_docs_inspect_form`、`tencent_docs_replace_form_questions`、`tencent_docs_publish_form`、`tencent_docs_build_and_publish_form`、`tencent_docs_create_and_publish_form`。
- 收集表正式 Open API：`tencent_docs_openapi_set_form_release`、`tencent_docs_openapi_generate_form_result`。
- 完整权限与协作者：`tencent_docs_openapi_get_user_access`、`get_file_permission`、`get_folder_permission`、`set_file_permission`、`apply_file_permission`、`add_collaborators`、`remove_collaborator`、`list_collaborators`、`transfer_ownership`。这些名称前都加 `tencent_docs_openapi_`。
- 文件扩展：收藏、置顶、水印、快捷方式、恢复文件、文件过滤、ID 转换、用量和未读数。使用 `tools --json` 取得精确参数。
- 表格图片：`tencent_docs_openapi_batch_insert_sheet_images`，支持一次批量插入最多 500 张已上传图片。

## 执行规则

1. 收集表修改前先调用 `tencent_docs_inspect_form`，确认链接、题目和权限。
2. 替换题目会覆盖整份表单的题目，必须先向用户展示完整新规格并取得明确确认。
3. 发布后必须检查返回的 `verified`；只有 `true` 才能报告公开版本已验证。
4. 永久删除、清空回收站、转让所有权和降低权限都必须获得用户对具体对象的确认，不得从“整理”“清理”等模糊请求推断。
5. 不得把 Cookie、Token、Client Secret、Open ID 或其他凭证写入对话、命令、文件或日志。

## 登录与 Open API

- 连接时 WorkBuddy 会打开 `docs.qq.com`。用户在常用浏览器登录后，CLI 只读取该浏览器中 `docs.qq.com` 的登录态，不把 Cookie 上传到 GitHub 或 AI 对话。
- 点击断开只禁止本连接器继续使用浏览器登录态，不会退出用户浏览器里的腾讯文档账号。
- `tencent_docs_openapi_*` 工具需要用户自己的腾讯文档开放平台应用。先调用 `tencent_docs_openapi_status`；如果未配置，调用 `tencent_docs_openapi_setup` 打开本机设置页。不要让用户在对话里粘贴 Client Secret。

## 错误处理

- “请重新连接腾讯文档”：让用户在 WorkBuddy 连接器页重新点击连接。
- “没有找到有效 TOK Cookie”：让用户在当前浏览器打开腾讯文档并登录。
- Windows 新版 Chrome/Edge 无法解密时，改用 Firefox 登录腾讯文档后重试。
- Open API 未配置或授权失效时，不得谎报成功；说明哪些工具受影响，其他收集表扩展仍可使用。
