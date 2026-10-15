"""实现劳动法律法规版本导入和当前有效法条检索。"""

from datetime import date
from typing import Any

from sqlalchemy import case, delete, func, not_, or_, select, update
from sqlalchemy.dialects.postgresql import insert

from agents.labor_law_agent.constants import LEGAL_STATUS_EFFECTIVE
from agents.labor_law_agent.schemas import EmbeddedArticle, LegalEvidence, ParsedLegalDocument
from agents.labor_law_agent.repository import LegalKnowledgeRepository
from app.db.database import PostgresDatabase
from app.models.legal_knowledge import LegalArticle, LegalDocument, LegalLawVersion


class PostgresLegalKnowledgeStore(LegalKnowledgeRepository):
    """PostgreSQL 法律知识库适配器，隔离法规 RAG 与 ORM 查询细节。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入应用共享数据库会话工厂和雪花 ID 生成器。"""
        self._database = database

    def upsert_law_version(
        self,
        document: ParsedLegalDocument,
        articles: list[EmbeddedArticle],
    ) -> int:
        """在单个事务中保存法规版本并替换该版本的法条向量。"""
        if not articles:
            raise ValueError("法规版本至少需要包含一条法条")
        with self._database.session_factory.begin() as session:
            law_statement = insert(LegalDocument).values(
                document_id=self._database.id_generator.next_id(),
                title=document.title,
                legal_type=document.legal_type,
                issuer=document.issuer,
                jurisdiction="中国大陆全国",
            )
            law_statement = law_statement.on_conflict_do_update(
                index_elements=[LegalDocument.title],
                set_={
                    "legal_type": law_statement.excluded.legal_type,
                    "issuer": law_statement.excluded.issuer,
                    "updated_at": func.now(),
                },
            ).returning(LegalDocument.document_id)
            document_id = session.execute(law_statement).scalar_one()

            session.execute(
                update(LegalLawVersion)
                .where(LegalLawVersion.document_id == document_id)
                .values(is_current=False)
            )
            version_statement = insert(LegalLawVersion).values(
                law_version_id=self._database.id_generator.next_id(),
                document_id=document_id,
                source_file=document.source_file,
                original_file=document.original_file,
                source_sha256=document.source_sha256,
                original_sha256=document.original_sha256,
                source_url=document.source_url,
                promulgated_on=_parse_date(document.promulgated_on),
                effective_on=_parse_date(document.effective_on),
                status=document.status,
                retrieved_on=date.fromisoformat(document.retrieved_on),
                is_current=True,
            )
            version_statement = version_statement.on_conflict_do_update(
                index_elements=[LegalLawVersion.document_id, LegalLawVersion.source_sha256],
                set_={
                    "source_file": version_statement.excluded.source_file,
                    "original_file": version_statement.excluded.original_file,
                    "original_sha256": version_statement.excluded.original_sha256,
                    "source_url": version_statement.excluded.source_url,
                    "promulgated_on": version_statement.excluded.promulgated_on,
                    "effective_on": version_statement.excluded.effective_on,
                    "status": version_statement.excluded.status,
                    "retrieved_on": version_statement.excluded.retrieved_on,
                    "is_current": True,
                },
            ).returning(LegalLawVersion.law_version_id)
            law_version_id = session.execute(version_statement).scalar_one()

            session.execute(
                delete(LegalArticle).where(LegalArticle.law_version_id == law_version_id)
            )
            session.add_all(
                [
                    LegalArticle(
                        article_id=self._database.id_generator.next_id(),
                        law_version_id=law_version_id,
                        article_no=item.article.article_no,
                        chapter=item.article.chapter,
                        section=item.article.section,
                        content=item.article.content,
                        embedding=item.embedding,
                    )
                    for item in articles
                ]
            )
        return law_version_id

    def search_keywords(
        self,
        terms: list[str],
        article_no: str | None,
        limit: int,
    ) -> list[LegalEvidence]:
        """对法条编号及关键词执行精确的当前版本检索。"""
        safe_terms = [_escape_like(term) for term in terms if term.strip()]
        match_count = sum(
            (
                case((LegalArticle.content.ilike(f"%{term}%", escape="\\"), 1), else_=0)
                for term in safe_terms
            ),
            start=0,
        )
        exact_article = LegalArticle.article_no == article_no if article_no else False
        conditions = [LegalLawVersion.is_current.is_(True), LegalLawVersion.status == LEGAL_STATUS_EFFECTIVE]
        if safe_terms:
            conditions.append(or_(match_count > 0, exact_article))
        elif article_no:
            conditions.append(exact_article)
        else:
            return []

        statement = (
            select(LegalArticle, LegalDocument.title, LegalLawVersion.source_url, LegalLawVersion.effective_on)
            .join(LegalLawVersion, LegalLawVersion.law_version_id == LegalArticle.law_version_id)
            .join(LegalDocument, LegalDocument.document_id == LegalLawVersion.document_id)
            .where(*conditions)
            .order_by(case((exact_article, 1), else_=0).desc(), match_count.desc())
            .limit(limit)
        )
        with self._database.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            _to_evidence(row, keyword_matches=int(row[0].article_no == article_no) + _count_matches(row[0].content, terms))
            for row in rows
        ]

    def search_vectors(self, embedding: list[float], limit: int) -> list[LegalEvidence]:
        """按余弦距离从当前有效法规版本中查找相似法条。"""
        distance = LegalArticle.embedding.cosine_distance(embedding).label("distance")
        statement = (
            select(
                LegalArticle,
                LegalDocument.title,
                LegalLawVersion.source_url,
                LegalLawVersion.effective_on,
                distance,
            )
            .join(LegalLawVersion, LegalLawVersion.law_version_id == LegalArticle.law_version_id)
            .join(LegalDocument, LegalDocument.document_id == LegalLawVersion.document_id)
            .where(
                LegalLawVersion.is_current.is_(True),
                LegalLawVersion.status == LEGAL_STATUS_EFFECTIVE,
            )
            .order_by(distance)
            .limit(limit)
        )
        with self._database.session_factory() as session:
            rows = session.execute(statement).all()
        return [
            _to_evidence(row, vector_similarity=max(0.0, 1.0 - float(row.distance)))
            for row in rows
        ]

    def deactivate_missing_laws(self, active_titles: set[str]) -> None:
        """停用同步清单已移除的法规，避免废止法规继续进入当前检索。"""
        active_document_ids = select(LegalDocument.document_id).where(
            LegalDocument.title.in_(active_titles)
        )
        statement = (
            update(LegalLawVersion)
            .where(
                LegalLawVersion.is_current.is_(True),
                not_(LegalLawVersion.document_id.in_(active_document_ids)),
            )
            .values(is_current=False)
        )
        with self._database.session_factory.begin() as session:
            session.execute(statement)


def _parse_date(value: str | None) -> date | None:
    """把官方 ISO 日期转换成数据库日期字段。"""
    return date.fromisoformat(value) if value else None


def _escape_like(value: str) -> str:
    """转义用户关键词中的 SQL LIKE 通配符。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _count_matches(content: str, terms: list[str]) -> int:
    """计算当前法条包含的关键词数量，用于融合排序。"""
    folded_content = content.casefold()
    return sum(term.casefold() in folded_content for term in set(terms) if term)


def _to_evidence(row: Any, **scores: float | int) -> LegalEvidence:
    """将 ORM 查询行转换为 RAG 模块使用的法条证据 DTO。"""
    article = row[0]
    effective_on = row[3]
    return LegalEvidence(
        article_id=str(article.article_id),
        title=row[1],
        article_no=article.article_no,
        chapter=article.chapter,
        section=article.section,
        content=article.content,
        source_url=row[2],
        effective_on=effective_on.isoformat() if effective_on else None,
        **scores,
    )

