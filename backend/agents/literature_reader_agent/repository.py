
from typing import Protocol

from agents.literature_reader_agent.schemas import LiteratureEvidence


class LiteratureRepository(Protocol):
    """文献问答图和检索服务依赖的持久化能力边界。"""

    def search_keywords(
        self, terms: list[str], document_ids: list[str], principal_id: str, limit: int
    ) -> list[LiteratureEvidence]:
        """在可信主体已选文献中执行关键词检索。"""
        ...

    def search_vectors(
        self,
        embedding: list[float],
        document_ids: list[str],
        principal_id: str,
        limit: int,
    ) -> list[LiteratureEvidence]:
        """在可信主体已选文献中执行 pgvector 近邻检索。"""
        ...

    def get_document_outline(
        self, document_id: str, principal_id: str, limit: int
    ) -> list[LiteratureEvidence]:
        """按原文顺序均匀抽取就绪文献片段，用于有界全文概览。"""
        ...

    def get_evidence_by_ids(
        self, evidence_ids: list[str], document_ids: list[str], principal_id: str
    ) -> list[LiteratureEvidence]:
        """按 ID 重读本轮证据并再次执行主体和文献范围过滤。"""
        ...
