---
name: tencent-docs-native-form
description: 通过 API 新建腾讯文档原生收集表，读取或替换问答题和选择题，设置匿名、发布并验证公开预览。当用户要求在腾讯文档做收集表、问卷、报名表或反馈表，且不使用浏览器自动化时使用。
---

# 腾讯文档原生收集表

通过本地 MCP 直接操作腾讯文档原生收集表，不点击页面。

## 执行顺序

1. Windows 上如果写入工具提示没有登录状态，调用 `tencent_docs_login`；等待用户登录，成功后继续原任务。
2. 用户没有提供现成表单、要求从零创建并发布时，调用 `tencent_docs_create_and_publish_form`。
3. 用户只要求新建空白表单时，调用 `tencent_docs_create_form`。
4. 用户提供了现成表单时，先调用 `tencent_docs_inspect_form`，确认链接、发布状态和当前账号权限。
5. 用户明确要求完整重建并发布现成表单时，调用 `tencent_docs_build_and_publish_form`。
6. 只改题目不发布时，调用 `tencent_docs_replace_form_questions`。
7. 只发布已经完成的草稿时，调用 `tencent_docs_publish_form`。
8. 对写入结果必须看工具返回的 `verified`；不得只根据 HTTP 成功宣称已完成。

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
