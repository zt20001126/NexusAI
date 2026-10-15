"""科研文献检索 REST API 的请求与响应 DTO。"""

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.research_agent.constants import (
    RESEARCH_DEFAULT_LIMIT,
    RESEARCH_MAX_REQUEST_CHARS,
    RESEARCH_MAX_LIMIT,
    RESEARCH_MIN_LIMIT,
    RESEARCH_MAX_YEAR,
    RESEARCH_MIN_YEAR,
)
from agents.research_agent.schemas import ResearchPaper, ResearchSort, ResearchStatus


class ResearchRequest(BaseModel):
    """一次科研文献检索请求；session_id 是现有会话 ID 的别名。"""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(
        min_length=2,
        max_length=RESEARCH_MAX_REQUEST_CHARS,
        description="研究主题或检索问题",
    )
    session_id: str | None = Field(
        default=None,
        pattern=r"^[1-9][0-9]{0,18}$",
        description="可选的数字雪花会话 ID",
    )
    limit: int = Field(
        default=RESEARCH_DEFAULT_LIMIT,
        ge=RESEARCH_MIN_LIMIT,
        le=RESEARCH_MAX_LIMIT,
        description="最多返回论文数",
    )
    year_from: int | None = Field(
        default=None,
        ge=RESEARCH_MIN_YEAR,
        le=RESEARCH_MAX_YEAR,
        description="起始出版年份",
    )
    year_to: int | None = Field(
        default=None,
        ge=RESEARCH_MIN_YEAR,
        le=RESEARCH_MAX_YEAR,
        description="结束出版年份",
    )
    language: str | None = Field(
        default=None,
        pattern=r"^[a-z]{2,3}$",
        description="可选 OpenAlex 语言代码，例如 en",
    )
    sort: ResearchSort | None = Field(default=None, description="可选论文排序方式")

    @model_validator(mode="after")
    def validate_year_range(self) -> "ResearchRequest":
        """拒绝空白查询及相互矛盾的结构化年份条件。"""
        if not self.message.strip():
            raise ValueError("检索主题不能为空")
        if (
            self.year_from is not None
            and self.year_to is not None
            and self.year_from > self.year_to
        ):
            raise ValueError("起始年份不能晚于结束年份")
        return self


class ResearchResponse(BaseModel):
    """一次检索执行完成后的结构化响应。"""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$", description="现有会话雪花 ID")
    status: ResearchStatus = Field(description="本次检索的业务状态")
    query: str = Field(description="原始用户查询")
    papers: list[ResearchPaper] = Field(description="已标准化的论文列表")
    returned_count: int = Field(ge=0, le=RESEARCH_MAX_LIMIT, description="返回论文数量")
    message: str = Field(description="面向用户的结果说明")
