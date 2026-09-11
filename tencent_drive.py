"""腾讯文档官方 MCP 尚未打包的文件管理能力。

接口来自腾讯文档网页当前的生产代码，属于未公开接口。
它们可能在腾讯文档改版后变更。
"""

from __future__ import annotations

from typing import Any, Literal

from tencent_form import BASE_URL, TencentDocsError, TencentFormClient

FileListSource = Literal["recent", "starred", "shared", "trash", "folder"]
LIST_ENDPOINTS: dict[FileListSource, str] = {
    "recent": "/api/list/recent",
    "starred": "/api/list/star",
    "shared": "/api/list/shared",
    "trash": "/api/list/trash",
    "folder": "/api/list/file",
}
PERSONAL_DOMAIN_ID = "300000000"


def _summary(item: dict[str, Any]) -> dict[str, Any]:
    entry = item.get("entry") or {}
    meta = item.get("meta") or {}
    file_id = str(entry.get("file_id") or meta.get("file_id") or "")
    return {
        "file_id": file_id,
        "name": entry.get("name") or meta.get("name") or "",
        "url": entry.get("doc_url") or meta.get("tencent_doc_url") or "",
        "is_folder": bool(entry.get("is_folder") or meta.get("is_folder")),
        "is_shortcut": bool(entry.get("is_link") or meta.get("is_link")),
        "is_starred": bool(entry.get("is_starred")),
        "is_pinned": bool(entry.get("is_pin")),
        "parent_id": str(entry.get("entry_parent_id") or meta.get("file_parent_id") or ""),
        "origin_folder_id": str(
            entry.get("source_parent_id")
            or entry.get("delete_position")
            or meta.get("file_parent_id")
            or ""
        ),
        "doc_type": item.get("doc_type"),
        "mime_type": item.get("mime_type") or "",
        "modified_at": entry.get("modify_time") or meta.get("modify_time"),
    }


class TencentDriveClient(TencentFormClient):
    """文件列表、收藏、恢复、快捷方式和版本查看。"""

    def _require_auth(self) -> None:
        if self.auth is None:
            raise TencentDocsError("文件管理需要登录腾讯文档。")

    def list_files(
        self,
        source: FileListSource,
        *,
        parent_id: str = "/",
        offset: int = 0,
        count: int = 50,
    ) -> dict[str, Any]:
        self._require_auth()
        path = LIST_ENDPOINTS[source]
        params: dict[str, Any] = {"offset": offset, "count": count}
        if source == "folder":
            params["parent_id"] = parent_id
        result = self._ensure_success(
            self._request_json(path, params=params, referer=BASE_URL + "/desktop"),
            "读取文件列表",
        )
        payload = result.get("result") or {}
        raw_files = payload.get("files") or []
        if not isinstance(raw_files, list):
            raise TencentDocsError("腾讯文档返回的文件列表格式异常。")
        return {
            "source": source,
            "files": [_summary(item) for item in raw_files if isinstance(item, dict)],
            "count": len(raw_files),
            "finished": bool(payload.get("finish", True)),
            "next_marker": payload.get("next_marker") or "",
            "total": payload.get("total_num"),
        }

    def set_starred(self, file_id: str, starred: bool) -> dict[str, Any]:
        self._require_auth()
        result = self._ensure_success(
            self._request_json(
                "/cgi-bin/online_docs/doc_collect",
                method="POST",
                form={
                    "domain_id": PERSONAL_DOMAIN_ID,
                    "pad_id": file_id,
                    "is_cancel": 0 if starred else 1,
                },
                referer=BASE_URL + "/desktop",
            ),
            "更新收藏状态",
        )
        return {"file_id": file_id, "starred": starred, "retcode": result.get("retcode")}

    def restore_file(self, file_id: str, origin_folder_id: str) -> dict[str, Any]:
        self._require_auth()
        result = self._ensure_success(
            self._request_json(
                "/cgi-bin/online_docs/doc_recover",
                method="POST",
                form={
                    "domain_id": PERSONAL_DOMAIN_ID,
                    "pad_id": file_id,
                    "origin_folder_id": origin_folder_id,
                },
                referer=BASE_URL + "/desktop/trash",
            ),
            "从回收站恢复文件",
        )
        return {"file_id": file_id, "restored": True, "retcode": result.get("retcode")}

    def add_shortcut(self, file_id: str, target_parent_id: str) -> dict[str, Any]:
        self._require_auth()
        result = self._ensure_success(
            self._request_json(
                "/api/create/link",
                method="POST",
                body={"file_id": file_id, "target_parent_id": target_parent_id},
                referer=BASE_URL + "/desktop",
            ),
            "添加快捷方式",
        )
        payload = result.get("result") or {}
        return {
            "file_id": file_id,
            "target_parent_id": target_parent_id,
            "shortcut_id": payload.get("link_id") or "",
            "already_exists": bool(payload.get("link_already_exist")),
        }

    def set_pinned(self, file_id: str, folder_id: str, pinned: bool) -> dict[str, Any]:
        self._require_auth()
        path = (
            "/cgi-bin/online_docs/doc_pin"
            if pinned
            else "/cgi-bin/online_docs/doc_unpin"
        )
        result = self._ensure_success(
            self._request_json(
                path,
                method="POST",
                form={
                    "domain_id": PERSONAL_DOMAIN_ID,
                    "pad_id": file_id,
                    "list_type": 2,
                    "folder_id": folder_id,
                    "version": 2,
                },
                referer=BASE_URL + "/desktop",
            ),
            "更新置顶状态",
        )
        return {
            "file_id": file_id,
            "folder_id": folder_id,
            "pinned": pinned,
            "retcode": result.get("retcode"),
        }

    def permanently_delete_trash_item(
        self,
        item_type: Literal["file", "folder"],
        item_id: str,
        origin_folder_id: str,
    ) -> dict[str, Any]:
        self._require_auth()
        if item_type == "file":
            path = "/cgi-bin/online_docs/trash_dropdoc"
            form = {
                "domain_id": PERSONAL_DOMAIN_ID,
                "origin_folder_id": origin_folder_id,
                "pad_id": item_id,
            }
        else:
            path = "/cgi-bin/online_docs/trash_dropfolder"
            form = {"origin_folder_id": origin_folder_id, "folder_id": item_id}
        self._ensure_success(
            self._request_json(
                path,
                method="POST",
                multipart=form,
                referer=BASE_URL + "/desktop/trash",
            ),
            "永久删除回收站项目",
        )
        return {
            "item_type": item_type,
            "item_id": item_id,
            "permanently_deleted": True,
        }

    def clear_trash(self) -> dict[str, Any]:
        self._require_auth()
        self._ensure_success(
            self._request_json(
                "/cgi-bin/online_docs/trash_clear",
                method="POST",
                referer=BASE_URL + "/desktop/trash",
            ),
            "清空回收站",
        )
        return {"trash_cleared": True}
