"""腾讯文档原生收集表 MCP 服务器。"""

from __future__ import annotations

import asyncio
from typing import Annotated, Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tencent_form import (
    TencentDocsError,
    TencentFormClient,
    build_form_data,
    compare_spec,
    load_auth,
    summarize_form,
)


mcp = MCPServer("腾讯文档原生收集表")
ResponseFormat = Literal["markdown", "json"]


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
    def validate_options(self) -> "QuestionSpec":
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
    if payload.get("verified") is not None:
        lines.append(f"公开版本验证：{'通过' if payload['verified'] else '未通过'}")
    return "\n".join(lines)


def _inspect_sync(form_url: str) -> dict:
    auth = load_auth(required=False)
    client = TencentFormClient(auth)
    result = client.fetch_form(form_url, "head")
    return summarize_form(result, auth.source if auth else "none")


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


if __name__ == "__main__":
    mcp.run()
