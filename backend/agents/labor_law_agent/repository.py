"""声明劳动法律知识库持久化端口，供智能体与 SQLAlchemy 适配器解耦。"""

from typing import Protocol

from agents.labor_law_agent.schemas import EmbeddedArticle, LegalEvidence, ParsedLegalDocument


class LegalKnowledgeRepository(Protocol):
    """法规版本导入和现行法条混合检索的持久化边界。"""

    def upsert_law_version(
        self,
        document: ParsedLegalDocument,
        articles: list[EmbeddedArticle],
    ) -> int:
        """保存法规元数据、版本快照和对应的法条向量。"""
        ...

    def search_keywords(
        self,
        terms: list[str],
        article_no: str | None,
        limit: int,
    ) -> list[LegalEvidence]:
        """对当前有效版本执行法条号和词项匹配。"""
        ...

    def search_vectors(self, embedding: list[float], limit: int) -> list[LegalEvidence]:
        """对当前有效版本执行 pgvector 余弦距离检索。"""
        ...

    def deactivate_missing_laws(self, active_titles: set[str]) -> None:
        """停用本次官方同步清单已不再包含的法规版本。"""
        ...

