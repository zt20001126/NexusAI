"""校验简历优化候选；该工具不访问数据库。"""

from datetime import datetime
from typing import Any, Literal

from langchain_core.tools import tool
from pydantic import BaseModel, ConfigDict, Field

from agent.schemas.tool_result import ToolResult


MAX_RESUME_CANDIDATE_ENTRIES = 20
MAX_INTENDED_POSITION_CHARS = 120
_PATCH_KEYS_BY_SCOPE: dict[str, frozenset[str]] = {
    "basic_info": frozenset({"basic_info"}),
    "educations": frozenset({"skills"}),
    "skills": frozenset({"skills"}),
    "works": frozenset({"works"}),
    "projects": frozenset({"projects"}),
    "all": frozenset({"basic_info", "skills", "works", "projects"}),
}


class ResumeOptimizationCandidate(BaseModel):
    """可优化职业字段及其来源版本。"""

    model_config = ConfigDict(extra="forbid")
    scope: Literal["basic_info", "educations", "skills", "works", "projects", "all"] = Field(
        description="本次优化范围；educations 仅表示教育与技能分组，教育事实字段不可改写。"
    )
    source_updated_at: str = Field(min_length=1, max_length=64)
    patch: dict = Field(
        description=(
            "仅包含所选范围允许字段：basic_info.intended_position；"
            "skills 为 Tiptap 文档；works/projects 为 [{index, content}]，"
            "content 使用 Tiptap JSON。不得提交身份、教育事实、雇主、职位或日期字段。"
        )
    )


@tool("stage_resume_optimization", args_schema=ResumeOptimizationCandidate)
def stage_resume_optimization(
    scope: str,
    source_updated_at: str,
    patch: dict[str, Any],
) -> str:
    """校验并返回可预览候选；不会保存或修改数据库。"""
    try:
        candidate = ResumeOptimizationCandidate(
            scope=scope,
            source_updated_at=source_updated_at,
            patch=patch,
        )
        _validate_candidate(candidate)
    except (TypeError, ValueError):
        return ToolResult(
            success=False,
            code="INVALID_RESUME_CANDIDATE",
            message="候选范围或字段结构无效，请按所选范围重新生成。",
        ).model_dump_json()

    return ToolResult(
        success=True,
        data=candidate.model_dump(mode="json"),
        message="候选结构已校验，可向用户展示并请求确认。",
    ).model_dump_json()


def _validate_candidate(candidate: ResumeOptimizationCandidate) -> None:
    """校验来源版本和范围字段，阻止候选包含受保护简历字段。"""
    source_updated_at = datetime.fromisoformat(candidate.source_updated_at)
    if source_updated_at.tzinfo is None:
        raise ValueError("简历版本时间必须包含时区")
    if not candidate.patch:
        raise ValueError("候选补丁不能为空")

    allowed_keys = _PATCH_KEYS_BY_SCOPE[candidate.scope]
    if set(candidate.patch) - allowed_keys:
        raise ValueError("补丁字段超出选择范围")

    basic_info = candidate.patch.get("basic_info")
    if basic_info is not None:
        if not isinstance(basic_info, dict) or set(basic_info) != {"intended_position"}:
            raise ValueError("基本信息候选只允许更新求职意向")
        position = basic_info["intended_position"]
        if (
            not isinstance(position, str)
            or not position.strip()
            or len(position) > MAX_INTENDED_POSITION_CHARS
        ):
            raise ValueError("求职意向不能为空或超过长度限制")

    skills = candidate.patch.get("skills")
    if skills is not None and not _is_tiptap_document(skills):
        raise ValueError("技能候选必须是有效的 Tiptap 文档结构")

    for field_name in ("works", "projects"):
        entries = candidate.patch.get(field_name)
        if entries is None:
            continue
        if not isinstance(entries, list) or len(entries) > MAX_RESUME_CANDIDATE_ENTRIES:
            raise ValueError("工作或项目候选条目无效")
        indexes: set[int] = set()
        for entry in entries:
            if (
                not isinstance(entry, dict)
                or set(entry) != {"index", "content"}
                or not isinstance(entry["index"], int)
                or isinstance(entry["index"], bool)
                or entry["index"] < 0
                or entry["index"] in indexes
                or not _is_tiptap_document(entry["content"])
            ):
                raise ValueError("工作或项目候选只能更新有效条目的正文")
            indexes.add(entry["index"])


def _is_tiptap_document(value: object) -> bool:
    """检查 Tiptap 根结构；完整节点与大小限制由简历 Schema 再校验。"""
    return (
        isinstance(value, dict)
        and value.get("type") == "doc"
        and isinstance(value.get("content"), list)
        and bool(value["content"])
    )
