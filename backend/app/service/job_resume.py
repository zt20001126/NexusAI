"""为求职助手读取固定主体简历并转换为有界求职事实。"""

import logging
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError

from agents.job_agent.resume_snapshot import (
    MAX_JOB_RESUME_FACTS_CHARS,
    JobResumeSnapshot,
    ResumeEducationFact,
    ResumeProjectFact,
    ResumeWorkFact,
)
from app.crud.resume import PostgresResumeRepository
from app.dependencies.resume_owner import get_resume_owner_principal_id
from app.schemas.resume import (
    ResumeContent,
    TiptapBulletList,
    TiptapDocument,
    TiptapHardBreak,
    TiptapListItem,
    TiptapOrderedList,
    TiptapParagraph,
)


logger = logging.getLogger(__name__)


class _TextBudget:
    """限制一次工具结果包含的简历文字总量。"""

    def __init__(self) -> None:
        self.remaining = MAX_JOB_RESUME_FACTS_CHARS
        self.truncated = False

    def take(self, text: str | None) -> str:
        """裁剪并计入一个字段，保留所有字段共享的剩余预算。"""

        normalized = (text or "").strip()
        kept = normalized[: self.remaining]
        self.remaining -= len(kept)
        if len(kept) < len(normalized):
            self.truncated = True
        return kept


class SavedJobResumeReader:
    """读取简历固定主体并只向求职助手提供经过筛选的简历事实。"""

    def __init__(self, repository: PostgresResumeRepository) -> None:
        self._repository = repository
        self._principal_id = get_resume_owner_principal_id()

    def read(self) -> JobResumeSnapshot:
        """读取已保存简历并校验后投影求职字段。

        Step 1: 使用固定主体从简历仓储读取一条记录。
        Step 2: 将 JSONB 内容校验为简历契约，提取求职相关字段。
        Step 3: 截断富文本并返回不含联系方式等敏感字段的 DTO。
        """

        try:
            record = self._repository.get(self._principal_id)
        except SQLAlchemyError as error:
            self._log_read_failure(error)
            return JobResumeSnapshot(status="unavailable")

        if record is None:
            return JobResumeSnapshot(status="not_found")

        try:
            content = ResumeContent.model_validate(record.content)
        except ValidationError as error:
            self._log_read_failure(error)
            return JobResumeSnapshot(status="unavailable")

        return _to_job_resume_snapshot(content, record.updated_at)

    @staticmethod
    def _log_read_failure(error: Exception) -> None:
        """记录失败类型，不把简历内容或驱动异常详情写入日志。"""

        logger.warning("读取已保存简历失败 error_type=%s", type(error).__name__)


def _to_job_resume_snapshot(
    content: ResumeContent,
    updated_at: datetime,
) -> JobResumeSnapshot:
    """投影简历模型中的求职事实并应用统一文本预算。"""

    budget = _TextBudget()
    info = content.basic_info
    intended_position = budget.take(info.intended_position) or None
    educations = [
        ResumeEducationFact(
            school=budget.take(item.school),
            major=budget.take(item.major),
            degree=budget.take(item.degree),
            start_month=budget.take(item.start_month),
            end_month=budget.take(item.end_month),
        )
        for item in content.educations
    ]
    skills = _document_text(content.skills, budget)
    works = [
        ResumeWorkFact(
            company=budget.take(item.company),
            position=budget.take(item.position),
            start_month=budget.take(item.start_month),
            end_month=budget.take(item.end_month),
            description=_document_text(item.content, budget),
        )
        for item in content.works
    ]
    projects = [
        ResumeProjectFact(
            name=budget.take(item.name),
            role=budget.take(item.role),
            technology_stack=budget.take(item.technology_stack),
            start_month=budget.take(item.start_month),
            end_month=budget.take(item.end_month),
            description=_document_text(item.content, budget),
        )
        for item in content.projects
    ]
    return JobResumeSnapshot(
        status="found",
        updated_at=updated_at,
        intended_position=intended_position,
        work_experience_years=info.work_experience_years,
        educations=educations,
        skills=skills,
        works=works,
        projects=projects,
        truncated=budget.truncated,
    )


def _document_text(document: TiptapDocument, budget: _TextBudget) -> str:
    """将已校验的 Tiptap 文档转换为带段落边界的纯文本。"""

    text = "\n".join(
        part for part in (_block_text(block) for block in document.content) if part
    )
    return budget.take(text)


def _block_text(
    block: TiptapParagraph | TiptapBulletList | TiptapOrderedList | TiptapListItem,
) -> str:
    """递归提取段落和列表块中的文本，不保留 HTML 或格式标记。"""

    if isinstance(block, TiptapParagraph):
        return "".join(
            "\n" if isinstance(part, TiptapHardBreak) else part.text
            for part in block.content
        ).strip()
    if isinstance(block, TiptapListItem):
        return "\n".join(
            part for part in (_block_text(item) for item in block.content) if part
        )
    if isinstance(block, (TiptapBulletList, TiptapOrderedList)):
        return "\n".join(
            part for part in (_block_text(item) for item in block.content) if part
        )
    return ""

