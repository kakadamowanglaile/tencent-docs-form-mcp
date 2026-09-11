"""腾讯文档原生收集表 MCP 服务器。"""

from __future__ import annotations

import asyncio
import time
from typing import Annotated, Any, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

from browser_login import login_with_browser
from official_mcp import OFFICIAL_MCP_URL, official_client
from openapi_auth import authorize_interactively, clear_openapi_tokens
from openapi_client import load_openapi_credentials, openapi_client
from openapi_setup_ui import open_setup_ui
from tencent_drive import FileListSource, TencentDriveClient
from tencent_form import (
    TencentDocsError,
    TencentFormClient,
    build_form_data,
    compare_spec,
    load_auth,
    summarize_form,
)

mcp = MCPServer("tencent_docs_mcp")
ResponseFormat = Literal["markdown", "json"]
BrowserChoice = Literal["auto", "chrome", "edge", "brave", "vivaldi", "chromium"]
PermissionPolicy = Literal["private", "members", "publicRead", "publicWrite"]


class QuestionSpec(BaseModel):
    """一道收集表问题。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: Literal["SIMPLE", "RADIO", "CHECKBOX", "SELECT"] = Field(
        description="题型：SIMPLE 问答、RADIO 单选、CHECKBOX 多选、SELECT 下拉选择。"
    )
    title: str = Field(min_length=1, max_length=200, description="问题标题。")
    subtitle: str = Field(default="", max_length=500, description="问题补充说明。")
    required: bool = Field(default=False, description="是否必填。")
    placeholder: str = Field(default="", max_length=100, description="输入或选择提示。")
    options: list[str] = Field(
        default_factory=list,
        max_length=50,
        description="选择题的选项；问答题必须留空。",
    )

    @model_validator(mode="after")
    def validate_options(self) -> QuestionSpec:
        if self.type == "SIMPLE" and self.options:
            raise ValueError("SIMPLE 问答题不能包含 options。")
        if self.type != "SIMPLE":
            if len(self.options) < 2:
                raise ValueError("选择题至少需要 2 个选项。")
            if any(not option.strip() for option in self.options):
                raise ValueError("选项不能为空。")
            if len(set(self.options)) != len(self.options):
                raise ValueError("选项不能重复。")
        return self


class FormSpec(BaseModel):
    """一份完整的腾讯文档收集表规格。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=100, description="收集表标题。")
    subtitle: str = Field(default="", max_length=1000, description="收集表说明。")
    questions: list[QuestionSpec] = Field(
        min_length=1,
        max_length=100,
        description="按显示顺序排列的问题。",
    )


class CollaboratorSpec(BaseModel):
    """腾讯文档公开 Open API 协作成员。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    open_id: str = Field(min_length=1, max_length=300, description="协作者的 Open ID。")
    role: Literal["reader", "writer"] = Field(
        description="reader 浏览者，writer 编辑者。"
    )


class SheetImageSpec(BaseModel):
    """在线表格批量插图的一张图片。"""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    type: Literal[1, 2] = Field(description="1 单元格图片，2 浮动图片。")
    url: str = Field(
        min_length=1,
        max_length=2000,
        description="官方 upload_image 返回的 imageID；批量接口字段名仍为 url。",
    )
    width: float = Field(gt=0, le=100000, description="图片宽度。")
    height: float = Field(gt=0, le=100000, description="图片高度。")
    row: int = Field(ge=1, le=1000000, description="目标行号，从 1 开始。")
    col: int = Field(ge=1, le=1000000, description="目标列号，从 1 开始。")
    offset_x: float | None = Field(default=None, description="浮动图片横向偏移。")
    offset_y: float | None = Field(default=None, description="浮动图片纵向偏移。")
    clip_info: dict[str, float] | None = Field(
        default=None,
        description="可选裁剪信息，例如 top、right、bottom、left。",
    )

    def to_openapi(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "url": self.url,
            "width": self.width,
            "height": self.height,
            "row": self.row,
            "col": self.col,
            "offsetX": self.offset_x,
            "offsetY": self.offset_y,
            "clip_info": self.clip_info,
        }


def _format_result(payload: dict, response_format: ResponseFormat) -> dict | str:
    if response_format == "json":
        return payload
    lines = [f"# {payload.get('title') or '腾讯文档收集表'}", ""]
    if "published" in payload:
        lines.extend(
            [
                f"- 已发布：{'是' if payload['published'] else '否'}",
                f"- 问题数：{payload.get('question_count', 0)}",
                f"- 已登录：{'是' if payload.get('is_login') else '否'}",
                f"- 创建者权限：{'是' if payload.get('is_owner') else '否'}",
            ]
        )
    if payload.get("stages"):
        lines.append("")
        lines.append("执行阶段：" + " → ".join(payload["stages"]))
    if payload.get("public_url"):
        lines.append("")
        lines.append(f"公开链接：{payload['public_url']}")
    elif payload.get("form_url"):
        lines.append("")
        lines.append(f"表单链接：{payload['form_url']}")
    if payload.get("verified") is not None:
        lines.append(f"公开版本验证：{'通过' if payload['verified'] else '未通过'}")
    return "\n".join(lines)


def _inspect_sync(form_url: str) -> dict:
    auth = load_auth(required=False)
    client = TencentFormClient(auth)
    result = client.fetch_form(form_url, "head")
    return summarize_form(result, auth.source if auth else "none")


def _create_sync(title: str) -> dict:
    auth = load_auth(required=True)
    client = TencentFormClient(auth)
    created = client.create_form(title)
    summary = summarize_form(client.fetch_form(created["form_url"], "head"), auth.source)
    return {**summary, **created}


def _replace_sync(form_url: str, spec: FormSpec) -> dict:
    auth = load_auth(required=True)
    client = TencentFormClient(auth)
    head = client.fetch_form(form_url, "head")
    server_data = head["data"]
    form_data = build_form_data(spec.model_dump(), server_data)
    saved = client.replace_form(form_url, form_data)
    verified_summary = summarize_form(client.fetch_form(form_url, "head"), auth.source)
    if not compare_spec(spec.model_dump(), verified_summary):
        raise TencentDocsError("保存请求成功，但回读结果与规格不一致。")
    return {
        **verified_summary,
        "saved_revision": (saved.get("data") or {}).get("rev"),
        "verified": True,
    }


def _publish_sync(form_url: str) -> dict:
    auth = load_auth(required=True)
    client = TencentFormClient(auth)
    client.publish(form_url)
    public_client = TencentFormClient(None)
    public_summary = summarize_form(public_client.fetch_form(form_url, "pub"), "none")
    if not public_summary["published"]:
        raise TencentDocsError("发布请求成功，但公开回读仍显示未发布。")
    return {**public_summary, "verified": True, "public_url": form_url}


def _build_publish_sync(form_url: str, spec: FormSpec, anonymous: bool) -> dict:
    auth = load_auth(required=True)
    client = TencentFormClient(auth)
    stages: list[str] = []
    head = client.fetch_form(form_url, "head")
    form_data = build_form_data(spec.model_dump(), head["data"])
    client.replace_form(form_url, form_data)
    stages.append("保存题目")

    draft_summary = summarize_form(client.fetch_form(form_url, "head"), auth.source)
    if not compare_spec(spec.model_dump(), draft_summary):
        raise TencentDocsError("题目回读验证未通过，已停止发布。")
    stages.append("验证草稿")

    client.set_anonymous(form_url, anonymous)
    stages.append("保存匿名设置")
    client.publish(form_url)
    stages.append("发布")

    public_client = TencentFormClient(None)
    public_summary = summarize_form(public_client.fetch_form(form_url, "pub"), "none")
    verified = public_summary["published"] and compare_spec(spec.model_dump(), public_summary)
    if not verified:
        raise TencentDocsError("发布后的公开版本与目标规格不一致。")
    stages.append("无登录公开回读验证")
    return {
        **public_summary,
        "verified": True,
        "anonymous": anonymous,
        "public_view_without_login": True,
        "public_url": form_url,
        "stages": stages,
        "notice": "匿名填写不等同于免登录填写；本次只验证了免登录查看。",
    }


def _create_build_publish_sync(spec: FormSpec, anonymous: bool) -> dict:
    auth = load_auth(required=True)
    created = TencentFormClient(auth).create_form(spec.title)
    result = _build_publish_sync(created["form_url"], spec, anonymous)
    return {**result, **created, "stages": ["新建收集表", *result["stages"]]}


def _official_status_sync(refresh: bool) -> dict:
    tools = official_client.list_tools(force_refresh=refresh)
    return {
        "connected": True,
        "endpoint": OFFICIAL_MCP_URL,
        "official_tool_count": len(tools),
        "token_source": official_client.token_source,
        "tool_schema_source": "live-tools-list",
    }


def _list_files_sync(
    source: FileListSource, parent_id: str, offset: int, count: int
) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).list_files(
        source, parent_id=parent_id, offset=offset, count=count
    )


def _set_starred_sync(file_id: str, starred: bool) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).set_starred(file_id, starred)


def _restore_file_sync(file_id: str, origin_folder_id: str) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).restore_file(file_id, origin_folder_id)


def _add_shortcut_sync(file_id: str, target_parent_id: str) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).add_shortcut(file_id, target_parent_id)


def _set_pinned_sync(file_id: str, folder_id: str, pinned: bool) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).set_pinned(file_id, folder_id, pinned)


def _permanently_delete_sync(
    item_type: Literal["file", "folder"], item_id: str, origin_folder_id: str
) -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).permanently_delete_trash_item(
        item_type, item_id, origin_folder_id
    )


def _clear_trash_sync() -> dict:
    auth = load_auth(required=True)
    return TencentDriveClient(auth).clear_trash()


@mcp.tool(
    title="登录腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_login(
    browser: Annotated[
        BrowserChoice,
        Field(description="auto 自动寻找可用浏览器，也可指定某一种浏览器。"),
    ] = "auto",
    timeout: Annotated[
        int, Field(ge=10, le=900, description="等待用户登录的秒数。")
    ] = 300,
) -> dict:
    """Windows 登录入口：弹出浏览器，登录成功后自动关窗并加密保存登录态。"""
    try:
        return await asyncio.to_thread(login_with_browser, browser, timeout)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="检查腾讯文档官方 MCP",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_official_status(
    refresh: Annotated[
        bool,
        Field(description="是否忽略 10 分钟工具清单缓存，重新读取官方 tools/list。"),
    ] = False,
) -> dict:
    """检查官方 MCP 授权和实时工具数，不返回 Token。"""
    try:
        return await asyncio.to_thread(_official_status_sync, refresh)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="读取腾讯文档文件列表",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_list_files(
    source: Annotated[
        FileListSource,
        Field(description="列表来源：recent、starred、shared、trash 或 folder。"),
    ] = "recent",
    parent_id: Annotated[
        str,
        Field(description="source=folder 时的文件夹 ID；根目录使用 /。"),
    ] = "/",
    offset: Annotated[int, Field(ge=0, le=100000)] = 0,
    count: Annotated[int, Field(ge=1, le=100)] = 50,
) -> dict:
    """读取最近、收藏、与我共享、回收站或指定文件夹。"""
    try:
        return await asyncio.to_thread(_list_files_sync, source, parent_id, offset, count)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="收藏或取消收藏腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_set_starred(
    file_id: Annotated[str, Field(min_length=1, max_length=200, description="文件 ID。")],
    starred: Annotated[bool, Field(description="true 收藏，false 取消收藏。")],
) -> dict:
    """修改文件收藏状态。"""
    try:
        return await asyncio.to_thread(_set_starred_sync, file_id, starred)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="从回收站恢复腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_restore_file(
    file_id: Annotated[str, Field(min_length=1, max_length=200, description="回收站文件 ID。")],
    origin_folder_id: Annotated[
        str,
        Field(min_length=1, max_length=200, description="回收站列表返回的 origin_folder_id。"),
    ],
) -> dict:
    """将回收站文件恢复到原文件夹。"""
    try:
        return await asyncio.to_thread(_restore_file_sync, file_id, origin_folder_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="添加腾讯文档快捷方式",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_add_shortcut(
    file_id: Annotated[str, Field(min_length=1, max_length=200, description="源文件 ID。")],
    target_parent_id: Annotated[
        str,
        Field(min_length=1, max_length=200, description="快捷方式所在的目标文件夹 ID。"),
    ],
) -> dict:
    """在指定文件夹中为现有文件添加快捷方式。"""
    try:
        return await asyncio.to_thread(_add_shortcut_sync, file_id, target_parent_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="置顶或取消置顶腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_set_pinned(
    file_id: Annotated[str, Field(min_length=1, max_length=200, description="文件 ID。")],
    folder_id: Annotated[
        str,
        Field(min_length=1, max_length=200, description="文件当前所在的文件夹 ID。"),
    ],
    pinned: Annotated[bool, Field(description="true 置顶，false 取消置顶。")],
) -> dict:
    """修改文件在当前文件夹中的置顶状态。"""
    try:
        return await asyncio.to_thread(_set_pinned_sync, file_id, folder_id, pinned)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="永久删除腾讯文档回收站项目",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_permanently_delete_trash_item(
    item_type: Annotated[Literal["file", "folder"], Field(description="项目类型。")],
    item_id: Annotated[str, Field(min_length=1, max_length=200, description="回收站项目 ID。")],
    origin_folder_id: Annotated[
        str,
        Field(min_length=1, max_length=200, description="回收站列表返回的 origin_folder_id。"),
    ],
    confirmation: Annotated[
        str,
        Field(description="必须精确填写：永久删除。"),
    ],
) -> dict:
    """不可恢复地删除一个回收站项目，必须由用户明确确认。"""
    if confirmation != "永久删除":
        raise ToolError("拒绝执行：confirmation 必须精确填写“永久删除”。")
    try:
        return await asyncio.to_thread(
            _permanently_delete_sync, item_type, item_id, origin_folder_id
        )
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="清空腾讯文档回收站",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_clear_trash(
    confirmation: Annotated[
        str,
        Field(description="必须精确填写：清空全部回收站。"),
    ],
) -> dict:
    """不可恢复地清空整个回收站，必须由用户明确确认。"""
    if confirmation != "清空全部回收站":
        raise ToolError(
            "拒绝执行：confirmation 必须精确填写“清空全部回收站”。"
        )
    try:
        return await asyncio.to_thread(_clear_trash_sync)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="新建腾讯文档收集表",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_create_form(
    title: Annotated[str, Field(min_length=1, max_length=100, description="新收集表的标题。")] = "无标题收集表",
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """使用当前登录账号新建一份空白的腾讯文档原生收集表。"""
    try:
        result = await asyncio.to_thread(_create_sync, title)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="检查腾讯文档收集表",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_inspect_form(
    form_url: Annotated[str, Field(description="腾讯文档原生收集表公开链接。")],
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """读取收集表标题、发布状态、题型和当前账号权限；不修改任何内容。"""
    try:
        result = await asyncio.to_thread(_inspect_sync, form_url)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="替换腾讯文档收集表题目",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_replace_form_questions(
    form_url: Annotated[str, Field(description="要修改的腾讯文档原生收集表链接。")],
    spec: FormSpec,
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """完整替换一份已存在的腾讯文档收集表题目，但不发布。

    只允许创建者或管理员执行。调用后会回读草稿并比对标题、题序和题型。
    """
    try:
        result = await asyncio.to_thread(_replace_sync, form_url, spec)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="发布腾讯文档收集表",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_publish_form(
    form_url: Annotated[str, Field(description="要立即发布的腾讯文档原生收集表链接。")],
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """立即发布当前草稿，然后在不带登录 Cookie 的情况下回读公开版本。"""
    try:
        result = await asyncio.to_thread(_publish_sync, form_url)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="生成并发布腾讯文档收集表",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_build_and_publish_form(
    form_url: Annotated[str, Field(description="要完整替换并发布的腾讯文档原生收集表链接。")],
    spec: FormSpec,
    anonymous: Annotated[
        bool,
        Field(description="是否隐藏填写者身份；这不等同于免登录填写。"),
    ] = False,
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """完整替换题目、保存匿名设置、发布，并以未登录请求验证公开版本。

    适用于“建好后直接给我可预览链接”的完整流程。它会替换当前表单的所有题目。
    """
    try:
        result = await asyncio.to_thread(_build_publish_sync, form_url, spec, anonymous)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="新建并发布腾讯文档收集表",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_create_and_publish_form(
    spec: FormSpec,
    anonymous: Annotated[
        bool,
        Field(description="是否隐藏填写者身份；这不等同于免登录填写。"),
    ] = False,
    response_format: Annotated[ResponseFormat, Field(description="返回 markdown 或 json。")] = "markdown",
) -> dict | str:
    """新建收集表、写入题目、发布，并以未登录请求验证公开版本。"""
    try:
        result = await asyncio.to_thread(_create_build_publish_sync, spec, anonymous)
        return _format_result(result, response_format)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="检查腾讯文档 Open API 配置",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_status(
    validate: Annotated[
        bool,
        Field(description="是否调用官方用户信息接口验证 Access Token。"),
    ] = False,
) -> dict:
    """检查正式 Open API 的本机配置；不返回 Token、Secret 或 Open ID。"""
    status = openapi_client.configuration_status()
    if validate:
        try:
            status["identity"] = await openapi_client.validate_identity()
        except TencentDocsError as exc:
            raise ToolError(str(exc)) from exc
    return status


@mcp.tool(
    title="打开腾讯文档 Open API 授权窗口",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_setup() -> dict:
    """打开仅限本机访问的设置页；首次配置应用，以后可直接点击授权。"""
    try:
        return await asyncio.to_thread(open_setup_ui)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="授权登录腾讯文档 Open API",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_login(
    timeout: Annotated[
        int,
        Field(ge=10, le=900, description="等待用户在官方页面授权的秒数。"),
    ] = 300,
) -> dict:
    """使用用户自己的开放平台应用，打开腾讯官方授权页并自动保存 Token。"""
    try:
        result = await asyncio.to_thread(authorize_interactively, timeout)
        openapi_client.credentials = load_openapi_credentials(required=True)
        return result
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="退出本机腾讯文档 Open API",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=False,
    ),
)
async def tencent_docs_openapi_logout() -> dict:
    """删除本机保存的用户 Token；应用配置保留，不会撤销腾讯账号端的授权。"""
    try:
        removed = await asyncio.to_thread(clear_openapi_tokens)
        openapi_client.credentials = None
        return {
            "local_tokens_removed": removed,
            "application_configuration_kept": True,
            "tencent_authorization_revoked": False,
        }
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="通过 Open API 收藏腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_set_starred(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    starred: Annotated[bool, Field(description="true 收藏，false 取消收藏。")],
) -> dict:
    """使用腾讯文档正式 Open API 修改文档收藏状态。"""
    try:
        return await openapi_client.set_starred(file_id, starred)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="通过 Open API 置顶腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_set_pinned(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    pinned: Annotated[bool, Field(description="true 置顶，false 取消置顶。")],
    folder_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="文档所在文件夹 ID；根目录为 /。"),
    ] = "/",
) -> dict:
    """使用腾讯文档正式 Open API 置顶或取消置顶自己的文档。"""
    try:
        return await openapi_client.set_pinned(file_id, pinned, folder_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="设置腾讯文档水印",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_set_watermark(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    text: Annotated[
        str,
        Field(max_length=500, description="自定义水印文字；空字符串表示取消文字水印。"),
    ] = "",
    visitor_mark: Annotated[bool, Field(description="是否显示访客身份水印。")]=False,
    margin: Annotated[
        Literal["loose", "tight"],
        Field(description="loose 宽松型，tight 密集型。"),
    ] = "loose",
    hide_from_owner: Annotated[
        bool,
        Field(description="是否对文档所有者隐藏水印。"),
    ] = True,
) -> dict:
    """设置正式 Open API 水印；收集表、流程图和思维导图不支持。"""
    try:
        return await openapi_client.set_watermark(
            file_id,
            text=text,
            visitor_mark=visitor_mark,
            margin=margin,
            hide_from_owner=hide_from_owner,
        )
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="通过 Open API 创建快捷方式",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_create_shortcut(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="源文档 fileID。")],
    target_folder_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="目标文件夹 ID；根目录为 /。"),
    ] = "/",
    share_key: Annotated[
        str,
        Field(max_length=500, description="共享文件夹场景所需的最外层 shareKey。"),
    ] = "",
) -> dict:
    """使用腾讯文档正式 Open API 创建文档快捷方式。"""
    try:
        return await openapi_client.create_shortcut(file_id, target_folder_id, share_key)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="通过 Open API 恢复腾讯文档",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_recover_file(
    file_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="回收站内、自身拥有的文档 fileID。"),
    ],
) -> dict:
    """使用腾讯文档正式 Open API 恢复回收站中的自有文档。"""
    try:
        return await openapi_client.recover_file(file_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查询腾讯文档用户访问权限",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_get_user_access(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
) -> dict:
    """查询当前授权用户的查看、编辑、下载、副本和水印权限。"""
    try:
        return await openapi_client.get_user_access(file_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查看腾讯文档完整分享权限",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_get_file_permission(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
) -> dict:
    """读取分享策略、复制下载打印和只读、可写批注设置。"""
    try:
        return await openapi_client.get_file_permission(file_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查询腾讯文档文件夹权限",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_get_folder_permission(
    folder_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="文件夹 folderID。"),
    ],
) -> dict:
    """读取当前用户对文件夹的查看、编辑、分享和添加成员能力。"""
    try:
        return await openapi_client.get_folder_permission(folder_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="转让腾讯文档所有权",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_transfer_ownership(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    owner_open_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="新所有者的 Open ID。"),
    ],
    confirmation: Annotated[
        str,
        Field(description="必须精确填写：转让所有权。"),
    ],
) -> dict:
    """把文档所有权转给指定用户；这是高影响操作，需要明确确认。"""
    if confirmation != "转让所有权":
        raise ToolError("拒绝执行：confirmation 必须精确填写“转让所有权”。")
    try:
        return await openapi_client.transfer_ownership(file_id, owner_open_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="设置完整腾讯文档权限",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_set_file_permission(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    policy: Annotated[
        PermissionPolicy | None,
        Field(description="private、members、publicRead 或 publicWrite；可不修改。"),
    ] = None,
    copy_enabled: Annotated[
        bool | None,
        Field(description="是否允许查看者复制、下载和打印；可不修改。"),
    ] = None,
    reader_comment_enabled: Annotated[
        bool | None,
        Field(description="是否允许只读者批注；可不修改。"),
    ] = None,
) -> dict:
    """设置官方 MCP 未暴露的完整分享权限，包括复制和只读批注开关。"""
    try:
        return await openapi_client.set_file_permission(
            file_id,
            policy=policy,
            copy_enabled=copy_enabled,
            reader_comment_enabled=reader_comment_enabled,
        )
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="申请腾讯文档权限",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_apply_file_permission(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    permission_type: Annotated[
        Literal["read", "write"],
        Field(description="read 申请查看，write 申请编辑。"),
    ],
    memo: Annotated[str, Field(max_length=500, description="申请备注。")]= "",
) -> dict:
    """通过正式 Open API 向文档所有者申请查看或编辑权限。"""
    try:
        return await openapi_client.apply_file_permission(file_id, permission_type, memo)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="添加腾讯文档协作成员",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_add_collaborators(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    collaborators: Annotated[
        list[CollaboratorSpec],
        Field(min_length=1, max_length=100, description="要添加的浏览者或编辑者。"),
    ],
) -> dict:
    """使用正式 Open API 批量添加指定 Open ID 的协作成员。"""
    payload = [
        {"type": "user", "role": item.role, "id": item.open_id}
        for item in collaborators
    ]
    try:
        return await openapi_client.add_collaborators(file_id, payload)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="移除腾讯文档协作成员",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=True,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_remove_collaborator(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
    collaborator_open_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="要移除的协作者 Open ID。"),
    ],
) -> dict:
    """使用正式 Open API 移除一个文档协作成员。"""
    try:
        return await openapi_client.remove_collaborator(file_id, collaborator_open_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查询腾讯文档协作成员",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_list_collaborators(
    file_id: Annotated[str, Field(min_length=1, max_length=300, description="文档 fileID。")],
) -> dict:
    """使用正式 Open API 查询文档的浏览者和编辑者列表。"""
    try:
        return await openapi_client.list_collaborators(file_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="按条件过滤腾讯文档",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_filter_files(
    list_type: Annotated[
        str,
        Field(min_length=1, max_length=100, description="官方列表类型，默认 folder。"),
    ] = "folder",
    sort_type: Annotated[
        str,
        Field(min_length=1, max_length=100, description="官方排序类型，默认 browse。"),
    ] = "browse",
    ascending: Annotated[bool, Field(description="是否正序排列。")]=False,
    folder_id: Annotated[
        str,
        Field(min_length=1, max_length=300, description="文件夹 ID；根目录为 /。"),
    ] = "/",
    start: Annotated[int, Field(ge=0, description="首次为 0，后续使用响应中的 next。")]=0,
    limit: Annotated[int, Field(ge=1, le=20, description="本次最多返回 20 条。")]=20,
    owned_only: Annotated[bool, Field(description="是否仅返回当前用户拥有的文件。")]=False,
    file_types: Annotated[
        str,
        Field(max_length=500, description="文件类型；多个类型用连字符分隔，空值表示全部。"),
    ] = "",
) -> dict:
    """调用正式列表过滤接口，支持目录、所有者、类型、排序和分页。"""
    try:
        return await openapi_client.filter_files(
            list_type=list_type,
            sort_type=sort_type,
            ascending=ascending,
            folder_id=folder_id,
            start=start,
            limit=limit,
            owned_only=owned_only,
            file_types=file_types,
        )
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="转换腾讯文档 fileID",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_convert_file_id(
    direction: Annotated[
        Literal["file_to_encoded", "encoded_to_file"],
        Field(description="file_to_encoded 或 encoded_to_file。"),
    ],
    value: Annotated[str, Field(min_length=1, max_length=500, description="要转换的 ID。")],
) -> dict:
    """在内部 fileID 与腾讯文档 URL 使用的 encodedID 之间转换。"""
    conversion_type = 1 if direction == "file_to_encoded" else 2
    try:
        return await openapi_client.convert_file_id(conversion_type, value)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查询腾讯文档 Open API 使用量",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_get_usage() -> dict:
    """查询当前开放平台应用的 Open API 资源总量和已使用数量。"""
    try:
        return await openapi_client.get_usage()
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="查询腾讯文档未读消息数",
    annotations=ToolAnnotations(read_only_hint=True, open_world_hint=True),
)
async def tencent_docs_openapi_get_unread_count() -> dict:
    """通过正式 Open API 查询当前用户的未读消息数量。"""
    try:
        return await openapi_client.get_unread_count()
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="设置腾讯文档收集表发布状态",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=True,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_set_form_release(
    form_id: Annotated[str, Field(min_length=1, max_length=300, description="收集表 formID。")],
    mode: Annotated[
        Literal["publish", "pause", "deadline"],
        Field(description="publish 永久发布，pause 暂停，deadline 到期停止。"),
    ],
    end_time: Annotated[
        int | None,
        Field(ge=1, description="mode=deadline 时必填，Unix 秒级时间戳。"),
    ] = None,
) -> dict:
    """使用正式 Open API 发布、暂停收集表或设置自动截止时间。"""
    now = int(time.time())
    if mode == "publish":
        resolved_end_time = 0
    elif mode == "pause":
        resolved_end_time = now - 1
    else:
        if end_time is None or end_time <= now:
            raise ToolError("mode=deadline 时 end_time 必须是未来的 Unix 秒级时间戳。")
        resolved_end_time = end_time
    try:
        return await openapi_client.set_form_release(form_id, resolved_end_time)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="生成腾讯文档收集结果",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_generate_form_result(
    form_id: Annotated[str, Field(min_length=1, max_length=300, description="收集表 formID。")],
) -> dict:
    """使用正式 Open API 生成收集结果表格，并返回关联文件信息。"""
    try:
        return await openapi_client.generate_form_result(form_id)
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


@mcp.tool(
    title="批量插入腾讯在线表格图片",
    annotations=ToolAnnotations(
        read_only_hint=False,
        destructive_hint=False,
        idempotent_hint=False,
        open_world_hint=True,
    ),
)
async def tencent_docs_openapi_batch_insert_sheet_images(
    book_id: Annotated[str, Field(min_length=1, max_length=300, description="在线表格 fileID。")],
    sheet_id: Annotated[str, Field(min_length=1, max_length=300, description="子表 sheetID。")],
    images: Annotated[
        list[SheetImageSpec],
        Field(min_length=1, max_length=500, description="一次最多插入 500 张图片。"),
    ],
) -> dict:
    """用 upload_image 返回的 imageID 批量插入单元格图片或浮动图片。"""
    try:
        return await openapi_client.batch_insert_sheet_images(
            book_id,
            sheet_id,
            [item.to_openapi() for item in images],
        )
    except TencentDocsError as exc:
        raise ToolError(str(exc)) from exc


if __name__ == "__main__":
    mcp.run()
