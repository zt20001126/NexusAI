"""科研文献检索计划、论文和结果的受校验数据结构。"""

from datetime import date, datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from agents.research_agent.constants import (
    RESEARCH_MAX_ABSTRACT_CHARS,
    RESEARCH_MAX_ALTERNATE_QUERIES,
    RESEARCH_MAX_AUTHOR_NAME_CHARS,
    RESEARCH_MAX_AUTHORS,
    RESEARCH_MAX_DOI_CHARS,
    RESEARCH_MAX_LIMIT,
    RESEARCH_MAX_QUERY_CHARS,
    RESEARCH_MAX_REQUEST_CHARS,
    RESEARCH_MAX_SEARCH_ROUNDS,
    RESEARCH_MAX_TITLE_CHARS,
    RESEARCH_MAX_URL_CHARS,
    RESEARCH_MAX_VENUE_CHARS,
    RESEARCH_MAX_YEAR,
    RESEARCH_MIN_YEAR,
    RESEARCH_MIN_LIMIT,
)

AlternativeResearchQuery = Annotated[
    str,
    Field(min_length=1, max_length=RESEARCH_MAX_QUERY_CHARS),
]
ResearchAuthor = Annotated[
    str,
    Field(min_length=1, max_length=RESEARCH_MAX_AUTHOR_NAME_CHARS),
]


class ResearchSort(StrEnum):
    """OpenAlex 返回论文的排序方式。"""

    RELEVANCE = "relevance"
    CITATION_COUNT = "citation_count"
    PUBLICATION_DATE = "publication_date"


class ResearchStatus(StrEnum):
    """一次检索对用户公开的业务状态。"""

    SUCCESS = "success"
    PARTIAL = "partial"
    NO_RESULTS = "no_results"
    FAILED = "failed"


class ResearchSearchPlan(BaseModel):
    """模型解析的检索词和硬性过滤条件；论文事实不由该模型生成。"""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(
        min_length=1,
        max_length=RESEARCH_MAX_QUERY_CHARS,
        description="用于 OpenAlex 全文检索的主题表达式",
    )
    alternative_queries: list[AlternativeResearchQuery] = Field(
        default_factory=list,
        max_length=RESEARCH_MAX_ALTERNATE_QUERIES,
        description="结果不足时使用的等义检索表达式",
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
        description="OpenAlex 语言代码，例如 en 或 zh",
    )
    sort: ResearchSort = Field(
        default=ResearchSort.RELEVANCE,
        description="结果排序方式",
    )

    @model_validator(mode="after")
    def validate_year_range(self) -> "ResearchSearchPlan":
        """拒绝颠倒的年份区间并清理空白查询词。"""
        self.query = self.query.strip()
        self.alternative_queries = [
            value.strip()
            for value in self.alternative_queries
            if value.strip() and value.strip().casefold() != self.query.casefold()
        ]
        if not self.query:
            raise ValueError("检索词不能为空")
        if self.year_from is not None and self.year_to is not None:
            if self.year_from > self.year_to:
                raise ValueError("起始年份不能晚于结束年份")
        return self


class ResearchPaper(BaseModel):
    """从单条 OpenAlex Work 记录映射得到的论文 DTO。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=RESEARCH_MAX_URL_CHARS,
        description="OpenAlex Work 标识",
    )
    title: str = Field(
        min_length=1,
        max_length=RESEARCH_MAX_TITLE_CHARS,
        description="论文标题",
    )
    authors: list[ResearchAuthor] = Field(
        max_length=RESEARCH_MAX_AUTHORS,
        description="作者显示名称",
    )
    year: int | None = Field(
        default=None,
        ge=RESEARCH_MIN_YEAR,
        le=RESEARCH_MAX_YEAR,
        description="出版年份",
    )
    language: str | None = Field(
        default=None,
        max_length=3,
        description="OpenAlex 语言代码",
    )
    publication_date: date | None = Field(default=None, description="出版日期")
    venue: str | None = Field(
        default=None,
        max_length=RESEARCH_MAX_VENUE_CHARS,
        description="期刊、会议或出版来源",
    )
    abstract: str | None = Field(
        default=None,
        max_length=RESEARCH_MAX_ABSTRACT_CHARS,
        description="由 OpenAlex 倒排索引重建的摘要",
    )
    doi: str | None = Field(
        default=None,
        max_length=RESEARCH_MAX_DOI_CHARS,
        description="规范化 DOI 标识",
    )
    citation_count: int = Field(ge=0, description="OpenAlex 引用次数")
    paper_url: str = Field(
        min_length=1,
        max_length=RESEARCH_MAX_URL_CHARS,
        description="论文或 OpenAlex Work 页面",
    )
    pdf_url: str | None = Field(
        default=None,
        max_length=RESEARCH_MAX_URL_CHARS,
        description="开放获取 PDF 地址",
    )
    source: str = Field(min_length=1, description="论文数据来源")


class ResearchSearchResult(BaseModel):
    """持久化并由结果详情接口返回的一次文献检索结果。"""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = Field(ge=1)
    status: ResearchStatus
    query: str
    message: str
    filters: dict[str, Any] = Field(default_factory=dict)
    returned_count: int = Field(ge=0, le=RESEARCH_MAX_LIMIT)
    source: str
    retrieved_at: datetime
    papers: list[ResearchPaper] = Field(max_length=RESEARCH_MAX_LIMIT)

    @model_validator(mode="after")
    def validate_paper_count(self) -> "ResearchSearchResult":
        """保持论文列表和数量字段一致。"""
        if self.returned_count != len(self.papers):
            raise ValueError("returned_count 必须等于 papers 长度")
        return self


class ResearchSearchToolInput(BaseModel):
    """受控搜索工具输入；运行身份由图节点从服务端状态注入。"""

    model_config = ConfigDict(extra="forbid")

    plan: ResearchSearchPlan = Field(description="经 Schema 校验的检索计划")
    limit: int = Field(ge=RESEARCH_MIN_LIMIT, le=RESEARCH_MAX_LIMIT, description="最大返回数量")
    original_request: str = Field(
        min_length=1,
        max_length=RESEARCH_MAX_REQUEST_CHARS,
        description="用户原始检索请求",
    )
    task_result_id: str = Field(min_length=1, max_length=64, description="服务端生成的结果标识")
    principal_id: str = Field(min_length=1, max_length=256, description="可信用户主体标识")
    conversation_id: str = Field(min_length=1, max_length=64, description="会话标识")
    run_id: str = Field(min_length=1, max_length=64, description="运行标识")
    agent_id: str = Field(min_length=1, max_length=64, description="注册的智能体标识")
    max_search_rounds: int = Field(
        ge=1,
        le=RESEARCH_MAX_SEARCH_ROUNDS,
        description="本次运行允许的 OpenAlex 查询轮数",
    )
