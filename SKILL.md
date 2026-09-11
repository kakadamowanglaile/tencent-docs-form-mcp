---
name: tencent-docs-complete
description: 通过统一 MCP 使用腾讯文档官方 MCP、官方未打包的正式 Open API，以及公开 API 仍未提供的收集表扩展。当用户要求不使用浏览器点击自动化操作腾讯文档时使用。
---

# 腾讯文档完整 MCP

工具优先级：官方 MCP → `tencent_docs_openapi_*` 正式 Open API → 必要时使用网页内部接口扩展。不要把网页内部接口说成腾讯公开 API。

## 执行顺序

1. Windows 上如果写入工具提示没有登录状态，调用 `tencent_docs_login`；等待用户登录，成功后继续原任务。
2. 用户没有提供现成表单、要求从零创建并发布时，调用 `tencent_docs_create_and_publish_form`。
3. 用户只要求新建空白表单时，调用 `tencent_docs_create_form`。
4. 用户提供了现成表单时，先调用 `tencent_docs_inspect_form`，确认链接、发布状态和当前账号权限。
5. 用户明确要求完整重建并发布现成表单时，调用 `tencent_docs_build_and_publish_form`。
6. 只改题目不发布时，调用 `tencent_docs_replace_form_questions`。
7. 只发布已经完成的草稿时，调用 `tencent_docs_publish_form`。
8. 对写入结果必须看工具返回的 `verified`；不得只根据 HTTP 成功宣称已完成。
9. 官方工具按其实时说明和 Schema 调用，不在 Skill 中假设参数。
10. 永久删除和清空回收站只能在用户当前请求明确要求时执行，不得根据“整理”或“清理”自行推断。
11. 收藏、置顶、恢复和快捷方式优先调用同名的 `tencent_docs_openapi_*` 工具；只有 Open API 未配置且用户接受网页接口限制时，才调用旧扩展工具。
12. 发布、暂停或设置收集截止时间时，优先调用 `tencent_docs_openapi_set_form_release`。
13. 转让所有权必须确认目标 Open ID，并由用户明确授权后填写工具要求的确认词。
14. `tencent_docs_openapi_status` 显示未授权时，若用户已运行 `openapi_setup.py` 保存自己的应用配置，调用 `tencent_docs_openapi_login`，并等待用户在腾讯官方页面确认。
15. 完整读取分享策略时使用 `tencent_docs_openapi_get_file_permission`；读取文件夹操作能力时使用 `tencent_docs_openapi_get_folder_permission`。

## 题型

- `SIMPLE`：问答题，`options` 留空。
- `RADIO`：单选题，至少两个选项。
- `CHECKBOX`：多选题，至少两个选项。
- `SELECT`：下拉选择，至少两个选项。

## 凭证与权限

- Windows 首次使用时运行 `browser_login.py`；它自动选择 Chrome、Edge、Brave、Vivaldi 或 Chromium，登录成功后自动关窗。
- Windows MCP 设置 `TENCENT_DOCS_USE_SAVED_LOGIN=1`，后续直接用 API，不再操作浏览器。
- 工具默认不扫描浏览器 Cookie。
- 仅当 MCP 环境显式设置 `TENCENT_DOCS_USE_BROWSER_COOKIES=1` 时，读取 `TENCENT_DOCS_BROWSER` 指定浏览器中 `docs.qq.com` 的 Cookie。
- 不存在 Chrome 时，Windows 登录助手会自动改用系统自带的 Edge。
- 也可用 `TENCENT_DOCS_COOKIE` 传入 Cookie header，但只能放在本场进程环境，不得让用户在对话里粘贴。
- 仅创建者或管理员能写入和发布。
- 任何返回内容都不得包含 Cookie、`TOK`、用户 ID 或其他会话凭证。
- 官方 MCP Token 不得写入项目、回答、日志或测试快照。
- 正式 Open API 使用单独的 `Client-Id`、`Open-Id`、`Access-Token`；这些值以及 Client Secret、Refresh Token 不得写入回答、日志或测试快照。
- 先调用 `tencent_docs_openapi_status` 检查配置；需要验证有效性时使用 `validate=true`。
- 每位用户使用自己的开放平台应用。Client Secret 只能通过 `openapi_setup.py` 的隐藏输入配置，不得要求用户在 AI 对话里粘贴。
- `tencent_docs_openapi_logout` 只删除本机 Token。用户如需撤销腾讯端授权，需在腾讯文档第三方应用授权管理中关闭。

## 已知限制

- 题目保存和表单设置使用腾讯文档网页自身的未公开接口，腾讯改版后可能需要更新。
- `anonymous=true` 是“匿名提交”，不代表“免登录填写”。
- 发布验收只能证明未登录用户可读取已发布的题目；免登录提交需另外验证账号和文档策略。

## 示例

### 生成并发布

`tencent_docs_build_and_publish_form`：

```json
{
  "form_url": "https://docs.qq.com/form/page/EXAMPLE",
  "spec": {
    "title": "活动报名",
    "subtitle": "请如实填写",
    "questions": [
      {"type": "SIMPLE", "title": "姓名", "required": true},
      {"type": "RADIO", "title": "是否参加", "required": true, "options": ["是", "否"]}
    ]
  },
  "anonymous": false,
  "response_format": "json"
}
```

### 仅检查

`tencent_docs_inspect_form`：

```json
{
  "form_url": "https://docs.qq.com/form/page/EXAMPLE",
  "response_format": "markdown"
}
```

### 仅发布已存草稿

`tencent_docs_publish_form`：

```json
{
  "form_url": "https://docs.qq.com/form/page/EXAMPLE",
  "response_format": "json"
}
```
