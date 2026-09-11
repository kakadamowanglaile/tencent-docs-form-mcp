# 安全说明

## 登录凭证

本项目需要腾讯文档登录态才能写入和发布。Windows 推荐通过 `browser_login.py` 登录；它只在登录阶段打开浏览器，成功后立即关闭，并使用 Windows DPAPI 加密保存登录状态。其他系统可显式设置 `TENCENT_DOCS_USE_BROWSER_COOKIES=1`，读取指定浏览器中 `docs.qq.com` 的 Cookie。

- Windows 保存的登录文件只能由当前 Windows 账号解密；解密后 Cookie 仅保留在本地 MCP 进程内存中。
- 工具返回值和日志不包含 Cookie、`TOK` 或用户 ID。
- 不要将 `TENCENT_DOCS_COOKIE` 写进仓库、截图或对话。
- 不要将 `TENCENT_DOCS_MCP_TOKEN` 写进仓库、截图或对话。本项目自动获得的 Token 只保留在进程内存。
- 不要提交 `TENCENT_DOCS_OPENAPI_CLIENT_SECRET`、`TENCENT_DOCS_OPENAPI_ACCESS_TOKEN` 或 `TENCENT_DOCS_OPENAPI_REFRESH_TOKEN`。正式 Open API 凭据只应放在本机 MCP 进程环境或操作系统安全存储中。
- Open API Token 刷新后只更新当前 MCP 进程内存；项目不会把新 Token 写入仓库。
- 只有创建者或管理员身份会被允许执行写入。

## 正式 Open API

正式 Open API 需要腾讯文档开放平台应用的 OAuth2 授权。项目只调用 `https://docs.qq.com`，不会把凭据转发到第三方服务。公开仓库不提供共享 Client Secret；每位使用者必须使用自己的开放平台应用并自行审核授权范围。

## 内部接口

题目编辑和设置操作使用腾讯文档当前网页自身调用的未公开接口。这些接口可能变更或停止工作。请只操作自己拥有或获得明确授权的收集表，并自行确认当地法律、账号政策和腾讯文档服务条款。

回收站单项永久删除和清空回收站不可恢复。MCP 工具要求精确确认词，但这不能代替客户端向用户展示实际删除范围。

## 报告问题

安全问题请通过 GitHub Security Advisory 私下报告，不要在公开 Issue 中提交 Cookie、表单 token 或账号信息。
