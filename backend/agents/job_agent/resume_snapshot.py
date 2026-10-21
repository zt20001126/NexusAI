"""定义求职助手读取已保存简历时使用的有限事实 DTO。"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# 限制单次工具结果中传递给模型的简历文本总量。
MAX_JOB_RESUME_FACTS_CHARS = 12_000
# 简历读取暂不可用时返回给模型的稳定错误码。
JOB_RESUME_UNAVAILABLE_TOOL_CODE = "RESUME_UNAVAILABLE"


class ResumeEducationFact(BaseModel):
    """求职分析需要的单条教育经历，不包含简历内部记录 ID。"""

    school: str = Field(description="学校名称")
    major: str = Field(description="专业")
    degree: str = Field(description="学历或学位")
    start_month: str = Field(description="开始月份")
    end_month: str = Field(description="结束月份")


class ResumeWorkFact(BaseModel):
    """从已保存工作经历中提取的职业事实。"""

    company: str = Field(description="公司或组织名称")
    position: str = Field(description="职位名称")
    start_month: str = Field(description="开始月份")
    end_month: str = Field(description="结束月份")
    description: str = Field(description="工作内容纯文本")


class ResumeProjectFact(BaseModel):
    """从已保存项目经历中提取的职业事实。"""

    name: str = Field(description="项目名称")
    role: str = Field(description="项目角色")
    technology_stack: str = Field(description="技术栈")
    start_month: str = Field(description="开始月份")
    end_month: str = Field(description="结束月份")
    description: str = Field(description="项目内容纯文本")


class JobResumeSnapshot(BaseModel):
    """求职助手工具结果；只承载有界求职事实与读取状态。"""

    model_config = ConfigDict(extra="forbid")

    status: Literal["found", "not_found", "unavailable"] = Field(
        description="读取状态：found 为已读取，not_found 为尚无简历，unavailable 为数据暂不可用。"
    )
    updated_at: datetime | None = Field(
        default=None,
        description="数据库中简历的最后更新时间；没有简历时为空。",
    )
    intended_position: str | None = Field(
        default=None,
        description="简历中填写的求职意向。",
    )
    work_experience_years: int | None = Field(
        default=None,
        description="用户手动填写的工作经验年限，不从日期推算。",
    )
    educations: list[ResumeEducationFact] = Field(
        default_factory=list,
        description="教育经历；不含姓名、联系方式和年龄。",
    )
    skills: str = Field(default="", description="专业技能纯文本。")
    works: list[ResumeWorkFact] = Field(
        default_factory=list,
        description="工作经历及其纯文本描述。",
    )
    projects: list[ResumeProjectFact] = Field(
        default_factory=list,
        description="项目经历及其纯文本描述。",
    )
    truncated: bool = Field(
        default=False,
        description="文本事实是否达到工具输出字符上限并被截断。",
    )

