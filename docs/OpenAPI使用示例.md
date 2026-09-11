# 腾讯文档正式 Open API 工具示例

这些工具通过本项目的标准 MCP 服务调用，Codex、Claude、WorkBuddy、Cursor 等客户端使用同一套工具名和参数。调用前先运行：

```text
tencent_docs_openapi_status {"validate": true}
```

如果返回未配置，请先完成腾讯文档开放平台 OAuth2 授权，并把凭据放入本机 MCP 进程环境。不要在对话中粘贴真实 Token 或 Client Secret。

## 设置收集表截止时间

```json
{
  "form_id": "300000000$EXAMPLE",
  "mode": "deadline",
  "end_time": 1798761600
}
```

工具：`tencent_docs_openapi_set_form_release`

- `publish`：发布并持续收集。
- `pause`：立即暂停收集。
- `deadline`：在指定 Unix 秒级时间戳停止收集。

## 添加协作成员

```json
{
  "file_id": "300000000$EXAMPLE",
  "collaborators": [
    {"open_id": "OPEN_ID_1", "role": "reader"},
    {"open_id": "OPEN_ID_2", "role": "writer"}
  ]
}
```

工具：`tencent_docs_openapi_add_collaborators`

先用 `tencent_docs_openapi_list_collaborators` 查询现有成员，避免重复操作。

## 限制复制、下载、打印和批注

```json
{
  "file_id": "300000000$EXAMPLE",
  "policy": "members",
  "copy_enabled": false,
  "reader_comment_enabled": false
}
```

工具：`tencent_docs_openapi_set_file_permission`

这是权限修改操作。AI 客户端应在执行前向用户显示目标文档和变更内容。

## 批量插入表格图片

先通过官方 `upload_image` 工具上传图片，再调用：

```json
{
  "book_id": "300000000$EXAMPLE",
  "sheet_id": "BBAAAA",
  "images": [
    {
      "type": 1,
      "url": "腾讯文档 upload_image 返回的 imageID",
      "width": 100,
      "height": 100,
      "row": 1,
      "col": 1
    }
  ]
}
```

工具：`tencent_docs_openapi_batch_insert_sheet_images`。官方请求体字段名虽然是 `url`，实际填写上传接口返回的 `imageID`；一次最多 500 张。

## 官方资料

- [OAuth2 授权流程](https://docs.qq.com/open/document/app/oauth2/)
- [文件管理接口索引](https://docs.qq.com/open/document/app/openapi/v2/file/)
- [收集表发布与截止时间](https://docs.qq.com/open/document/app/openapi/v2/form/publish.html)
- [生成收集结果](https://docs.qq.com/open/document/app/openapi/v2/form/result.html)
- [表格批量插入图片](https://docs.qq.com/open/document/app/openapi/v2/sheet/requests/InsertImages.html)
