
from __future__ import annotations

from sqlalchemy import case, delete, func, literal, or_, select, update

from agents.literature_reader_agent.chunker import sample_evenly
from agents.literature_reader_agent.constants import (
    DOCUMENT_STATUS_QUEUED,
    DOCUMENT_STATUS_READY,
    LITERATURE_READER_AGENT,
)
from agents.literature_reader_agent.schemas import (
    EmbeddedLiteratureChunk,
    LiteratureDocumentRecord,
    LiteratureEvidence,
)
from agent.errors import ConversationAccessDeniedError
from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.literature import (
    LiteratureChunk,
    LiteratureConversationDocument,
    LiteratureDocument,
)
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresLiteratureRepository:
    """文献仓储，集中执行主体过滤、状态变更和证据查询。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享 PostgreSQL Session 工厂和雪花 ID 生成器。"""
        self._database = database

    def create_document(
        self,
        *,
        document_id: str,
        principal_id: str,
        title: str,
        source_type: str,
        source_url: str | None,
        file_name: str | None,
        object_key: str | None,
        content_type: str,
        file_size: int | None,
        content_sha256: str | None,
    ) -> LiteratureDocumentRecord:
        """创建 queued 文献记录并在需要时建立可信主体映射。"""
        with self._database.session_factory.begin() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=True,
                id_generator=self._database.id_generator,
            )
            record = LiteratureDocument(
                document_id=to_database_id(document_id),
                owner_id=owner_id,
                title=title,
                source_type=source_type,
                source_url=source_url,
                file_name=file_name,
                object_key=object_key,
                content_type=content_type,
                file_size=file_size,
                content_sha256=content_sha256,
                status=DOCUMENT_STATUS_QUEUED,
            )
            session.add(record)
            session.flush()
            return _to_record(record, principal_id)

    def get_owned_document(
        self, document_id: str, principal_id: str
    ) -> LiteratureDocumentRecord | None:
        """按文献 ID 和可信主体读取文献，越权数据不返回。"""
        with self._database.session_factory() as session:
            row = session.execute(
                select(LiteratureDocument, User.account.label("principal_id"))
                .join(User, User.user_id == LiteratureDocument.owner_id)
                .where(
                    LiteratureDocument.document_id == to_database_id(document_id),
                    User.account == principal_id,
                )
            ).one_or_none()
        return _to_record(row[0], row[1]) if row else None

    def get_document_for_task(self, document_id: str) -> LiteratureDocumentRecord | None:
        """读取 Worker 任务的文献及其所有者可信主体。"""
        with self._database.session_factory() as session:
            row = session.execute(
                select(LiteratureDocument, User.account.label("principal_id"))
                .join(User, User.user_id == LiteratureDocument.owner_id)
                .where(LiteratureDocument.document_id == to_database_id(document_id))
            ).one_or_none()
        return _to_record(row[0], row[1]) if row else None

    def list_documents(
        self, principal_id: str, *, limit: int, offset: int
    ) -> list[LiteratureDocumentRecord]:
        """按主体和更新时间倒序分页查询文献库。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return []
            records = session.scalars(
                select(LiteratureDocument)
                .where(LiteratureDocument.owner_id == owner_id)
                .order_by(
                    LiteratureDocument.updated_at.desc(),
                    LiteratureDocument.document_id.desc(),
                )
                .limit(limit)
                .offset(offset)
            ).all()
        return [_to_record(record, principal_id) for record in records]

    def count_documents(self, principal_id: str) -> int:
        """统计可信主体文献数量，用于生成分页 has_more。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return 0
            return int(
                session.scalar(
                    select(func.count())
                    .select_from(LiteratureDocument)
                    .where(LiteratureDocument.owner_id == owner_id)
                )
                or 0
            )

    def get_owned_ready_documents(
        self, document_ids: list[str], principal_id: str
    ) -> list[LiteratureDocumentRecord]:
        """确认所有所选文献归属当前主体且已完成解析。"""
        numeric_ids = [to_database_id(item) for item in document_ids]
        with self._database.session_factory() as session:
            rows = session.execute(
                select(LiteratureDocument, User.account.label("principal_id"))
                .join(User, User.user_id == LiteratureDocument.owner_id)
                .where(
                    LiteratureDocument.document_id.in_(numeric_ids),
                    User.account == principal_id,
                )
            ).all()
        records = [_to_record(row[0], row[1]) for row in rows]
        if len(records) != len(numeric_ids):
            from agent.errors import LiteratureDocumentNotFoundError

            raise LiteratureDocumentNotFoundError()
        if any(record.status != DOCUMENT_STATUS_READY for record in records):
            from agent.errors import LiteratureDocumentNotReadyError

            raise LiteratureDocumentNotReadyError()
        return sorted(records, key=lambda item: numeric_ids.index(to_database_id(item.document_id)))

    def update_status(
        self,
        document_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """更新异步入库任务状态和面向用户的安全失败原因。"""
        with self._database.session_factory.begin() as session:
            session.execute(
                update(LiteratureDocument)
                .where(LiteratureDocument.document_id == to_database_id(document_id))
                .values(
                    status=status,
                    error_code=error_code,
                    error_message=error_message,
                    updated_at=func.now(),
                )
            )

    def complete_ingestion(
        self,
        document_id: str,
        *,
        title: str,
        source_type: str,
        content_type: str,
        file_size: int,
        content_sha256: str,
        page_count: int | None,
        object_key: str | None,
        chunks: list[EmbeddedLiteratureChunk],
    ) -> None:
        """在同一事务内替换旧分块并将文献标记为 ready。"""
        with self._database.session_factory.begin() as session:
            record = session.get(
                LiteratureDocument, to_database_id(document_id), with_for_update=True
            )
            if record is None or record.status == "deleted":
                return
            session.execute(
                delete(LiteratureChunk).where(
                    LiteratureChunk.document_id == record.document_id
                )
            )
            for embedded in chunks:
                chunk = embedded.chunk
                session.add(
                    LiteratureChunk(
                        chunk_id=self._database.id_generator.next_id(),
                        document_id=record.document_id,
                        chunk_index=chunk.chunk_index,
                        content=chunk.content,
                        chapter=chunk.chapter,
                        section=chunk.section,
                        page_start=chunk.page_start,
                        page_end=chunk.page_end,
                        paragraph_start=chunk.paragraph_start,
                        paragraph_end=chunk.paragraph_end,
                        embedding=embedded.embedding,
                    )
                )
            record.title = title
            record.source_type = source_type
            record.content_type = content_type
            record.file_size = file_size
            record.content_sha256 = content_sha256
            record.page_count = page_count
            record.object_key = object_key or record.object_key
            record.status = DOCUMENT_STATUS_READY
            record.error_code = None
            record.error_message = None
            record.updated_at = func.now()

    def delete_owned_document(
        self, document_id: str, principal_id: str
    ) -> str | None:
        """删除主体文献及其数据库级联分块、会话关系并返回 OSS 对象键。"""
        with self._database.session_factory.begin() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                from agent.errors import LiteratureDocumentNotFoundError

                raise LiteratureDocumentNotFoundError()
            record = session.scalar(
                select(LiteratureDocument).where(
                    LiteratureDocument.document_id == to_database_id(document_id),
                    LiteratureDocument.owner_id == owner_id,
                )
            )
            if record is None:
                from agent.errors import LiteratureDocumentNotFoundError

                raise LiteratureDocumentNotFoundError()
            object_key = record.object_key
            session.delete(record)
            return object_key

    def search_keywords(
        self,
        terms: list[str],
        document_ids: list[str],
        principal_id: str,
        limit: int,
    ) -> list[LiteratureEvidence]:
        """在当前主体已就绪的所选文献中按词项召回正文分块。"""
        if not terms or not document_ids:
            return []
        conditions = [LiteratureChunk.content.contains(term, autoescape=True) for term in terms]
        score = sum(
            (case((condition, 1), else_=0) for condition in conditions),
            literal(0),
        )
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return []
            rows = session.execute(
                select(LiteratureChunk, LiteratureDocument, score.label("keyword_matches"))
                .join(
                    LiteratureDocument,
                    LiteratureDocument.document_id == LiteratureChunk.document_id,
                )
                .where(
                    LiteratureDocument.owner_id == owner_id,
                    LiteratureDocument.status == DOCUMENT_STATUS_READY,
                    LiteratureDocument.document_id.in_([to_database_id(item) for item in document_ids]),
                    or_(*conditions),
                )
                .order_by(score.desc(), LiteratureChunk.chunk_index)
                .limit(limit)
            ).all()
        return [
            _to_evidence(chunk, document, keyword_matches=int(matches))
            for chunk, document, matches in rows
        ]

    def search_vectors(
        self,
        embedding: list[float],
        document_ids: list[str],
        principal_id: str,
        limit: int,
    ) -> list[LiteratureEvidence]:
        """在当前主体已就绪的所选文献中按 pgvector 余弦距离召回分块。"""
        if not document_ids:
            return []
        distance = LiteratureChunk.embedding.cosine_distance(embedding)
        similarity = (1 - distance).label("vector_similarity")
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return []
            rows = session.execute(
                select(LiteratureChunk, LiteratureDocument, similarity)
                .join(
                    LiteratureDocument,
                    LiteratureDocument.document_id == LiteratureChunk.document_id,
                )
                .where(
                    LiteratureDocument.owner_id == owner_id,
                    LiteratureDocument.status == DOCUMENT_STATUS_READY,
                    LiteratureDocument.document_id.in_([to_database_id(item) for item in document_ids]),
                )
                .order_by(distance)
                .limit(limit)
            ).all()
        return [
            _to_evidence(chunk, document, vector_similarity=float(score))
            for chunk, document, score in rows
        ]

    def get_document_outline(
        self, document_id: str, principal_id: str, limit: int
    ) -> list[LiteratureEvidence]:
        """按文献原文顺序均匀取样，给总结任务提供跨章节证据。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return []
            chunk_ids = session.scalars(
                select(LiteratureChunk.chunk_id)
                .join(
                    LiteratureDocument,
                    LiteratureDocument.document_id == LiteratureChunk.document_id,
                )
                .where(
                    LiteratureDocument.document_id == to_database_id(document_id),
                    LiteratureDocument.owner_id == owner_id,
                    LiteratureDocument.status == DOCUMENT_STATUS_READY,
                )
                .order_by(LiteratureChunk.chunk_index)
            ).all()
        selected_ids = [chunk_ids[index] for index in sample_evenly(len(chunk_ids), limit)]
        if not selected_ids:
            return []
        evidence_by_id = {
            item.evidence_id: item
            for item in self.get_evidence_by_ids(
                [str(chunk_id) for chunk_id in selected_ids],
                [document_id],
                principal_id,
            )
        }
        return [evidence_by_id[str(chunk_id)] for chunk_id in selected_ids if str(chunk_id) in evidence_by_id]

    def get_evidence_by_ids(
        self,
        evidence_ids: list[str],
        document_ids: list[str],
        principal_id: str,
    ) -> list[LiteratureEvidence]:
        """按检索证据 ID 重新读取原文，重复验证文献主体和选择范围。"""
        if not evidence_ids or not document_ids:
            return []
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return []
            rows = session.execute(
                select(LiteratureChunk, LiteratureDocument)
                .join(
                    LiteratureDocument,
                    LiteratureDocument.document_id == LiteratureChunk.document_id,
                )
                .where(
                    LiteratureChunk.chunk_id.in_([to_database_id(item) for item in evidence_ids]),
                    LiteratureDocument.document_id.in_([to_database_id(item) for item in document_ids]),
                    LiteratureDocument.owner_id == owner_id,
                    LiteratureDocument.status == DOCUMENT_STATUS_READY,
                )
            ).all()
        return [_to_evidence(chunk, document) for chunk, document in rows]

    def get_conversation_document_ids(
        self, conversation_id: str, principal_id: str
    ) -> list[str] | None:
        """验证会话属于当前主体和文献助手后返回关联文献 ID。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return None
            conversation = session.scalar(
                select(Conversation.conversation_id).where(
                    Conversation.conversation_id == to_database_id(conversation_id),
                    Conversation.owner_id == owner_id,
                    Conversation.agent == LITERATURE_READER_AGENT.value,
                )
            )
            if conversation is None:
                return None
            values = session.scalars(
                select(LiteratureConversationDocument.document_id)
                .where(
                    LiteratureConversationDocument.conversation_id == conversation,
                )
                .order_by(LiteratureConversationDocument.added_at),
            ).all()
        return [str(value) for value in values]

    def get_conversation_documents(
        self, conversation_id: str, principal_id: str
    ) -> list[LiteratureDocumentRecord] | None:
        """验证会话归属和智能体后读取关联文献摘要所需记录。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return None
            conversation_id_value = session.scalar(
                select(Conversation.conversation_id).where(
                    Conversation.conversation_id == to_database_id(conversation_id),
                    Conversation.owner_id == owner_id,
                    Conversation.agent == LITERATURE_READER_AGENT.value,
                )
            )
            if conversation_id_value is None:
                return None
            rows = session.execute(
                select(LiteratureDocument, LiteratureConversationDocument.added_at)
                .join(
                    LiteratureConversationDocument,
                    LiteratureConversationDocument.document_id ==
                    LiteratureDocument.document_id,
                )
                .where(
                    LiteratureConversationDocument.conversation_id ==
                    conversation_id_value,
                )
                .order_by(LiteratureConversationDocument.added_at),
            ).all()
        return [_to_record(row[0], principal_id) for row in rows]

    def set_conversation_documents(
        self,
        conversation_id: str,
        document_ids: list[str],
        principal_id: str,
    ) -> None:
        """原子替换会话文献关系并再次核验所有权和 ready 状态。"""
        numeric_ids = [to_database_id(item) for item in document_ids]
        with self._database.session_factory.begin() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            conversation = session.scalar(
                select(Conversation).where(
                    Conversation.conversation_id == to_database_id(conversation_id),
                    Conversation.owner_id == owner_id,
                    Conversation.agent == LITERATURE_READER_AGENT.value,
                )
            ) if owner_id is not None else None
            if conversation is None:
                raise ConversationAccessDeniedError()
            owned_ready_ids = set(
                session.scalars(
                    select(LiteratureDocument.document_id).where(
                        LiteratureDocument.document_id.in_(numeric_ids),
                        LiteratureDocument.owner_id == owner_id,
                        LiteratureDocument.status == DOCUMENT_STATUS_READY,
                    )
                ).all()
            )
            if owned_ready_ids != set(numeric_ids):
                from agent.errors import LiteratureDocumentNotFoundError

                raise LiteratureDocumentNotFoundError()
            session.execute(
                delete(LiteratureConversationDocument).where(
                    LiteratureConversationDocument.conversation_id ==
                    conversation.conversation_id,
                )
            )
            session.add_all(
                LiteratureConversationDocument(
                    conversation_id=conversation.conversation_id,
                    document_id=document_id,
                )
                for document_id in numeric_ids
            )


def _to_record(
    record: LiteratureDocument, principal_id: str
) -> LiteratureDocumentRecord:
    """将 ORM 文献记录转换为内部类型化记录。"""
    return LiteratureDocumentRecord(
        document_id=str(record.document_id),
        owner_principal=principal_id,
        title=record.title,
        source_type=record.source_type,
        source_url=record.source_url,
        file_name=record.file_name,
        object_key=record.object_key,
        content_type=record.content_type,
        file_size=record.file_size,
        content_sha256=record.content_sha256,
        status=record.status,
        error_code=record.error_code,
        error_message=record.error_message,
        page_count=record.page_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _to_evidence(
    chunk: LiteratureChunk,
    document: LiteratureDocument,
    *,
    vector_similarity: float = 0.0,
    keyword_matches: int = 0,
) -> LiteratureEvidence:
    """将 ORM 分块和文献元数据组装为检索节点可用的证据对象。"""
    return LiteratureEvidence(
        evidence_id=str(chunk.chunk_id),
        document_id=str(document.document_id),
        title=document.title,
        source_type=document.source_type,
        source_url=document.source_url,
        chapter=chunk.chapter,
        section=chunk.section,
        page_start=chunk.page_start,
        page_end=chunk.page_end,
        paragraph_start=chunk.paragraph_start,
        paragraph_end=chunk.paragraph_end,
        content=chunk.content,
        vector_similarity=vector_similarity,
        keyword_matches=keyword_matches,
    )
