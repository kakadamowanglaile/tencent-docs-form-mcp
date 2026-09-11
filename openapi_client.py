"""腾讯文档正式 Open API 客户端。

这里仅调用腾讯文档开放平台公开文档中的接口。凭据从进程环境或
操作系统密钥库读取，不会写入项目文件，也不会出现在工具返回值中。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, replace
from typing import Any, Awaitable, Callable
from urllib.parse import quote

import httpx2

from tencent_form import TencentDocsError

OPENAPI_BASE_URL = "https://docs.qq.com"
CLIENT_ID_ENV = "TENCENT_DOCS_OPENAPI_CLIENT_ID"
CLIENT_SECRET_ENV = "TENCENT_DOCS_OPENAPI_CLIENT_SECRET"
ACCESS_TOKEN_ENV = "TENCENT_DOCS_OPENAPI_ACCESS_TOKEN"
REFRESH_TOKEN_ENV = "TENCENT_DOCS_OPENAPI_REFRESH_TOKEN"
OPEN_ID_ENV = "TENCENT_DOCS_OPENAPI_OPEN_ID"


@dataclass(frozen=True)
class OpenAPICredentials:
    """腾讯文档 Open API OAuth2 凭据。"""

    client_id: str
    open_id: str = ""
    access_token: str = ""
    client_secret: str = ""
    refresh_token: str = ""

    @property
    def can_refresh(self) -> bool:
        return bool(self.client_id and self.client_secret and self.refresh_token)

    @property
    def can_call(self) -> bool:
        return bool(self.client_id and self.open_id and self.access_token)


def load_openapi_credentials(required: bool = False) -> OpenAPICredentials | None:
    """从环境变量或操作系统密钥库读取 Open API 凭据。"""

    environment_credentials = OpenAPICredentials(
        client_id=os.environ.get(CLIENT_ID_ENV, "").strip(),
        client_secret=os.environ.get(CLIENT_SECRET_ENV, "").strip(),
        open_id=os.environ.get(OPEN_ID_ENV, "").strip(),
        access_token=os.environ.get(ACCESS_TOKEN_ENV, "").strip(),
        refresh_token=os.environ.get(REFRESH_TOKEN_ENV, "").strip(),
    )
    if environment_credentials.can_call or environment_credentials.can_refresh:
        return environment_credentials
    try:
        from openapi_auth import load_openapi_profile

        profile = load_openapi_profile(required=False)
    except TencentDocsError:
        profile = None
    if profile is not None:
        credentials = OpenAPICredentials(
            client_id=environment_credentials.client_id or profile.client_id,
            client_secret=environment_credentials.client_secret or profile.client_secret,
            open_id=environment_credentials.open_id or profile.open_id,
            access_token=environment_credentials.access_token or profile.access_token,
            refresh_token=environment_credentials.refresh_token or profile.refresh_token,
        )
        if credentials.can_call or credentials.can_refresh:
            return credentials
    if required:
        raise TencentDocsError(
            "腾讯文档 Open API 尚未授权。请先运行 openapi_setup.py，"
            "或在 MCP 进程环境中提供 Open API 凭据。"
        )
    return None


Requester = Callable[..., Awaitable[Any]]


def _segment(value: str, label: str) -> str:
    """把外部 ID 安全地放入 URL 路径段。"""

    normalized = value.strip()
    if not normalized:
        raise TencentDocsError(f"{label} 不能为空。")
    return quote(normalized, safe="$")


class TencentDocsOpenAPIClient:
    """公开 Open API 的异步客户端，支持 Access Token 失效后刷新一次。"""

    def __init__(
        self,
        credentials: OpenAPICredentials | None = None,
        *,
        timeout: float = 30.0,
        requester: Requester | None = None,
    ) -> None:
        self.credentials = credentials
        self.timeout = timeout
        self._requester = requester

    def configuration_status(self) -> dict[str, Any]:
        credentials = self.credentials or load_openapi_credentials(required=False)
        try:
            from openapi_auth import load_openapi_profile

            profile = load_openapi_profile(required=False)
        except TencentDocsError:
            profile = None
        return {
            "configured": bool(credentials and (credentials.can_call or credentials.can_refresh)),
            "app_configured": bool(profile and profile.app_configured)
            or bool(credentials and credentials.client_id and credentials.client_secret),
            "authorized": bool(credentials and credentials.can_call),
            "client_id_configured": bool(credentials and credentials.client_id),
            "open_id_configured": bool(credentials and credentials.open_id),
            "access_token_configured": bool(credentials and credentials.access_token),
            "automatic_refresh_configured": bool(credentials and credentials.can_refresh),
            "base_url": OPENAPI_BASE_URL,
        }

    async def _send(self, method: str, url: str, **kwargs: Any) -> Any:
        if self._requester is not None:
            return await self._requester(method, url, **kwargs)
        async with httpx2.AsyncClient(timeout=self.timeout) as client:
            return await client.request(method, url, **kwargs)

    async def _refresh(self) -> None:
        credentials = self.credentials or load_openapi_credentials(required=True)
        assert credentials is not None
        if not credentials.can_refresh:
            raise TencentDocsError(
                "腾讯文档 Open API Access Token 已失效，且没有配置可用于刷新的 "
                "Client Secret 和 Refresh Token。"
            )
        try:
            response = await self._send(
                "GET",
                OPENAPI_BASE_URL + "/oauth/v2/token",
                params={
                    "client_id": credentials.client_id,
                    "client_secret": credentials.client_secret,
                    "grant_type": "refresh_token",
                    "refresh_token": credentials.refresh_token,
                },
            )
        except Exception as exc:
            raise TencentDocsError("无法连接腾讯文档 Token 接口。") from exc
        if response.status_code >= 400:
            raise TencentDocsError(
                f"刷新腾讯文档 Open API Token 失败，HTTP {response.status_code}。"
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise TencentDocsError("腾讯文档 Token 接口返回了无法解析的数据。") from exc
        token = str(payload.get("access_token") or "").strip()
        open_id = str(payload.get("user_id") or credentials.open_id).strip()
        if not token or not open_id:
            raise TencentDocsError("腾讯文档 Token 接口没有返回 Access Token 或 Open ID。")
        refreshed_token = str(payload.get("refresh_token") or "").strip()
        self.credentials = replace(
            credentials,
            access_token=token,
            open_id=open_id,
            refresh_token=refreshed_token or credentials.refresh_token,
        )
        try:
            from openapi_auth import update_saved_openapi_tokens

            update_saved_openapi_tokens(
                client_id=credentials.client_id,
                open_id=open_id,
                access_token=token,
                refresh_token=refreshed_token or None,
                expires_in=int(payload.get("expires_in") or 0) or None,
            )
        except TencentDocsError:
            # 环境变量模式可能没有本机凭据库，不影响当前请求。
            pass

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        form: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_refresh: bool = True,
    ) -> dict[str, Any]:
        """调用公开接口并把官方业务错误转换成可处理的 MCP 错误。"""

        credentials = self.credentials or load_openapi_credentials(required=True)
        assert credentials is not None
        self.credentials = credentials
        if not credentials.can_call:
            await self._refresh()
            credentials = self.credentials
            assert credentials is not None

        headers = {
            "Accept": "application/json",
            "Access-Token": credentials.access_token,
            "Client-Id": credentials.client_id,
            "Open-Id": credentials.open_id,
        }
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        elif form is not None:
            headers["Content-Type"] = "application/x-www-form-urlencoded"

        try:
            response = await self._send(
                method,
                OPENAPI_BASE_URL + path,
                headers=headers,
                params=params,
                data=form,
                json=json_body,
            )
        except Exception as exc:
            raise TencentDocsError("无法连接腾讯文档 Open API。") from exc
        if response.status_code >= 400:
            raise TencentDocsError(
                f"腾讯文档 Open API 请求失败，HTTP {response.status_code}。"
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise TencentDocsError("腾讯文档 Open API 返回了无法解析的数据。") from exc
        if not isinstance(payload, dict):
            raise TencentDocsError("腾讯文档 Open API 返回的数据结构异常。")

        ret = payload.get("ret")
        if ret == 37019 and retry_refresh and credentials.can_refresh:
            await self._refresh()
            return await self.request(
                method,
                path,
                params=params,
                form=form,
                json_body=json_body,
                retry_refresh=False,
            )
        if ret not in (None, 0):
            message = str(payload.get("msg") or "未提供错误说明")
            raise TencentDocsError(f"腾讯文档 Open API 错误 {ret}：{message}。")
        return payload

    async def validate_identity(self) -> dict[str, Any]:
        credentials = self.credentials or load_openapi_credentials(required=True)
        assert credentials is not None
        if not credentials.access_token and credentials.can_refresh:
            await self._refresh()
            credentials = self.credentials
            assert credentials is not None
        try:
            response = await self._send(
                "GET",
                OPENAPI_BASE_URL + "/oauth/v2/userinfo",
                params={"access_token": credentials.access_token},
                headers={"Accept": "application/json"},
            )
        except Exception as exc:
            raise TencentDocsError("无法连接腾讯文档用户信息接口。") from exc
        if response.status_code >= 400:
            raise TencentDocsError(
                f"校验腾讯文档 Open API 身份失败，HTTP {response.status_code}。"
            )
        try:
            payload = response.json()
        except Exception as exc:
            raise TencentDocsError("腾讯文档用户信息接口返回了无法解析的数据。") from exc
        if not isinstance(payload, dict):
            raise TencentDocsError("腾讯文档用户信息接口返回的数据结构异常。")
        if payload.get("ret") not in (None, 0):
            raise TencentDocsError(
                f"腾讯文档 Open API 身份错误 {payload.get('ret')}："
                f"{payload.get('msg') or '未提供错误说明'}。"
            )
        data = payload.get("data") or {}
        return {
            "valid": True,
            "open_id_matches": bool(
                not credentials.open_id or data.get("openID") == credentials.open_id
            ),
            "source": data.get("source") or "",
        }

    async def set_starred(self, file_id: str, starred: bool) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "PATCH", f"/openapi/drive/v2/files/{file_path}/star", form={"star": 1 if starred else 2}
        )

    async def set_pinned(self, file_id: str, pinned: bool, folder_id: str = "/") -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "PATCH",
            f"/openapi/drive/v2/files/{file_path}/pin",
            form={"pin": 1 if pinned else 2, "folderID": folder_id},
        )

    async def set_watermark(
        self,
        file_id: str,
        *,
        text: str,
        visitor_mark: bool,
        margin: str,
        hide_from_owner: bool,
    ) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "PATCH",
            f"/openapi/drive/v2/files/{file_path}/watermark",
            form={
                "text": text,
                "visitorMark": 1 if visitor_mark else 2,
                "margin": margin,
                "hideFromOwner": 1 if hide_from_owner else 2,
            },
        )

    async def create_shortcut(
        self, file_id: str, target_folder_id: str = "/", share_key: str = ""
    ) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        form: dict[str, Any] = {"targetfolderID": target_folder_id}
        if share_key:
            form["shareKey"] = share_key
        return await self.request(
            "POST", f"/openapi/drive/v2/files/{file_path}/shortcut", form=form
        )

    async def recover_file(self, file_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request("PATCH", f"/openapi/drive/v2/files/{file_path}/recover")

    async def get_user_access(self, file_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request("GET", f"/openapi/drive/v2/files/{file_path}/access")

    async def get_file_permission(self, file_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "GET", f"/openapi/drive/v2/files/{file_path}/permission"
        )

    async def get_folder_permission(self, folder_id: str) -> dict[str, Any]:
        folder_path = _segment(folder_id, "folderID")
        return await self.request(
            "GET", f"/openapi/drive/v2/folders/{folder_path}/permission"
        )

    async def transfer_ownership(self, file_id: str, owner_open_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "PATCH",
            f"/openapi/drive/v2/files/{file_path}/ownership",
            form={"ownerID": owner_open_id},
        )

    async def set_file_permission(
        self,
        file_id: str,
        *,
        policy: str | None,
        copy_enabled: bool | None,
        reader_comment_enabled: bool | None,
    ) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        form: dict[str, Any] = {}
        if policy is not None:
            form["policy"] = policy
        if copy_enabled is not None:
            form["copyEnabled"] = str(copy_enabled).lower()
        if reader_comment_enabled is not None:
            form["readerCommentEnabled"] = str(reader_comment_enabled).lower()
        if not form:
            raise TencentDocsError("至少提供一项要修改的文档权限。")
        return await self.request(
            "PATCH", f"/openapi/drive/v2/files/{file_path}/permission", form=form
        )

    async def apply_file_permission(
        self, file_id: str, permission_type: str, memo: str = ""
    ) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        form = {"type": permission_type}
        if memo:
            form["memo"] = memo
        return await self.request(
            "POST", f"/openapi/drive/v2/files/{file_path}/permission/apply", form=form
        )

    async def add_collaborators(
        self, file_id: str, collaborators: list[dict[str, str]]
    ) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "PATCH",
            f"/openapi/drive/v2/files/{file_path}/collaborators",
            json_body={"collaborators": collaborators},
        )

    async def remove_collaborator(self, file_id: str, open_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "DELETE",
            f"/openapi/drive/v2/files/{file_path}/collaborators",
            params={"type": "user", "id": open_id},
        )

    async def list_collaborators(self, file_id: str) -> dict[str, Any]:
        file_path = _segment(file_id, "fileID")
        return await self.request(
            "GET", f"/openapi/drive/v2/files/{file_path}/collaborators"
        )

    async def filter_files(
        self,
        *,
        list_type: str,
        sort_type: str,
        ascending: bool,
        folder_id: str,
        start: int,
        limit: int,
        owned_only: bool,
        file_types: str,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "listType": list_type,
            "sortType": sort_type,
            "asc": 1 if ascending else 0,
            "folderID": folder_id,
            "start": start,
            "limit": limit,
            "isOwner": 2 if owned_only else 1,
        }
        if file_types:
            params["fileType"] = file_types
        return await self.request("GET", "/openapi/drive/v2/filter", params=params)

    async def convert_file_id(self, conversion_type: int, value: str) -> dict[str, Any]:
        return await self.request(
            "GET",
            "/openapi/drive/v2/util/converter",
            params={"type": conversion_type, "value": value},
        )

    async def get_usage(self) -> dict[str, Any]:
        return await self.request("GET", "/openapi/drive/v2/util/resource-use")

    async def get_unread_count(self) -> dict[str, Any]:
        return await self.request("GET", "/openapi/drive/v2/notification/unread-count")

    async def set_form_release(self, form_id: str, end_time: int) -> dict[str, Any]:
        form_path = _segment(form_id, "formID")
        return await self.request(
            "PUT", f"/openapi/drive/v2/forms/{form_path}/release", form={"endTime": end_time}
        )

    async def generate_form_result(self, form_id: str) -> dict[str, Any]:
        form_path = _segment(form_id, "formID")
        return await self.request(
            "POST", f"/openapi/drive/v2/forms/{form_path}/result", form={}
        )

    async def batch_insert_sheet_images(
        self, book_id: str, sheet_id: str, images: list[dict[str, Any]]
    ) -> dict[str, Any]:
        book_path = _segment(book_id, "bookID")
        return await self.request(
            "POST",
            f"/openapi/sheetbook/v2/{book_path}:batchUpdate",
            json_body={
                "bookID": book_id,
                "insertImages": {"sheetID": sheet_id, "images": images},
            },
        )


openapi_client = TencentDocsOpenAPIClient()
