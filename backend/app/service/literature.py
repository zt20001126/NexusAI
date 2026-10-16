
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import AsyncIterator
from typing import Any, Protocol

from agent.errors import (
    ConversationAccessDeniedError,
    LiteratureDocumentNotFoundError,
    LiteratureDocumentNotReadyError,
    LiteratureQueueUnavailableError,
)
from agent.streaming.events import AgentEvent, AgentEventType
from agents.literature_reader_agent.constants import (
    DOCUMENT_STATUS_FAILED,
    LITERATURE_READER_AGENT_ID,
    LITERATURE_AGENT_MAX_DOCUMENTS,
    SOURCE_TYPE_PDF_UPLOAD,
)
from agents.literature_reader_agent.schemas import (
    LiteratureDocumentRecord,
)
from app.schemas.literature import (
    ConversationLiteratureDocumentsResponse,
    DocumentCreatedResponse,
    LiteratureDocumentSummary,
    LiteratureDocumentsResponse,
)
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator

logger = logging.getLogger(__name__)
_SAFE_FILE_NAME_PATTERN = re.compile(r"[\\x00-\\x1f\\x7f]+")


class LiteratureRepositoryPort(Protocol):
    """应用服务依赖的文献仓储操作边界。"""

    def create_document(self, **values: Any) -> LiteratureDocumentRecord: ...

    def get_owned_document(
        self, document_id: str, principal_id: str
    ) -> LiteratureDocumentRecord | None: ...

    def list_documents(
        self, principal_id: str, *, limit: int, offset: int
    ) -> list[LiteratureDocumentRecord]: ...

    def count_documents(self, principal_id: str) -> int: ...

    def get_owned_ready_documents(
        self, document_ids: list[str], principal_id: str
    ) -> list[LiteratureDocumentRecord]: ...

    def update_status(
        self,
        document_id: str,
        status: str,
        *,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None: ...

    def delete_owned_document(
        self, document_id: str, principal_id: str
    ) -> str | None: ...

    def get_conversation_document_ids(
        self, conversation_id: str, principal_id: str
    ) -> list[str] | None: ...

    def get_conversation_documents(
        self, conversation_id: str, principal_id: str
    ) -> list[LiteratureDocumentRecord] | None: ...

    def set_conversation_documents(
        self, conversation_id: str, document_ids: list[str], principal_id: str
    ) -> None: ...


class LiteratureDocumentStorage(Protocol):
    """文献 PDF 对象存储所需的保存、读取和删除能力。"""

    def save_pdf(
        self, principal_id: str, document_id: str, file_name: str, pdf_bytes: bytes
    ) -> str: ...

    def delete_pdf(self, principal_id: str, object_key: str) -> None: ...


class LiteratureTaskQueue(Protocol):
    """文献异步入库消息发送能力边界。"""

    def enqueue(self, document_id: str) -> None: ...


class LiteratureApplicationService:
    """编排文献文件、队列、可信主体、会话范围和智能体运行。"""

    def __init__(
        self,
        *,
        repository: LiteratureRepositoryPort,
        storage: LiteratureDocumentStorage,
        task_queue: LiteratureTaskQueue,
        chat_service: Any,
        settings: AppSettings,
        id_generator: SnowflakeIdGenerator | None = None,
    ) -> None:
        """注入文献仓储、私有 OSS、Celery、聊天服务和资源配置。"""
        self._repository = repository
        self._storage = storage
        self._task_queue = task_queue
        self._chat_service = chat_service
        self._settings = settings
        self._id_generator = id_generator or get_snowflake_generator(
            settings.snowflake_worker_id
        )

    def upload_pdf(
        self, *, principal_id: str, file_name: str, pdf_bytes: bytes
    ) -> DocumentCreatedResponse:
        """保存 PDF 原件并创建异步入库任务。\n\n        Step 1: 校验文件大小和 PDF 文件签名。\n        Step 2: 生成文献 ID，将原件写入主体私有 OSS 路径。\n        Step 3: 创建 queued 数据记录并提交只包含文献 ID 的 Celery 任务。\n        """
        if not pdf_bytes or len(pdf_bytes) > self._settings.literature_upload_max_bytes:
            raise ValueError("PDF 文件为空或超过服务端上传上限")
        if b"%PDF-" not in pdf_bytes[:1_024]:
            raise ValueError("上传内容不是有效 PDF 文件")
        safe_file_name = _safe_file_name(file_name)
        document_id = self._id_generator.next_id_string()
        object_key = self._storage.save_pdf(
            principal_id, document_id, safe_file_name, pdf_bytes
        )
        return self._create_and_enqueue(
            document_id=document_id,
            principal_id=principal_id,
            title=safe_file_name,
            source_type=SOURCE_TYPE_PDF_UPLOAD,
            source_url=None,
            file_name=safe_file_name,
            object_key=object_key,
            content_type="application/pdf",
            file_size=len(pdf_bytes),
            content_sha256=hashlib.sha256(pdf_bytes).hexdigest(),
        )

    def _create_and_enqueue(self, **values: Any) -> DocumentCreatedResponse:
        """先持久化文献记录，再排队；Broker 异常写入可见失败状态。"""
        try:
            self._repository.create_document(**values)
        except Exception:
            object_key = values.get("object_key")
            if object_key:
                try:
                    self._storage.delete_pdf(values["principal_id"], object_key)
                except Exception as cleanup_error:
                    logger.warning(
                        "文献记录创建失败且 OSS 清理未完成 error_type=%s",
                        type(cleanup_error).__name__,
                    )
            raise
        document_id = values["document_id"]
        try:
            self._task_queue.enqueue(document_id)
        except Exception as error:
            logger.warning(
                "文献入库任务提交失败 document_id=%s error_type=%s",
                document_id,
                type(error).__name__,
            )
            self._repository.update_status(
                document_id,
                DOCUMENT_STATUS_FAILED,
                error_code="QUEUE_UNAVAILABLE",
                error_message="文献处理队列暂时不可用，请稍后重试。",
            )
            raise LiteratureQueueUnavailableError() from error
        return DocumentCreatedResponse(document_id=document_id, status="queued")

    def list_documents(
        self, *, principal_id: str, limit: int, offset: int
    ) -> LiteratureDocumentsResponse:
        """查询当前可信主体文献库并组装分页响应。"""
        records = self._repository.list_documents(
            principal_id, limit=limit + 1, offset=offset
        )
        has_more = len(records) > limit
        return LiteratureDocumentsResponse(
            items=[_to_summary(item) for item in records[:limit]],
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    def get_document(
        self, *, document_id: str, principal_id: str
    ) -> LiteratureDocumentSummary:
        """按可信主体读取单篇文献和入库状态。"""
        record = self._repository.get_owned_document(document_id, principal_id)
        if record is None:
            raise LiteratureDocumentNotFoundError()
        return _to_summary(record)

    def delete_document(self, *, document_id: str, principal_id: str) -> None:
        """先验证归属并删除 OSS 原件，再清理数据库文献和级联关系。"""
        record = self._repository.get_owned_document(document_id, principal_id)
        if record is None:
            raise LiteratureDocumentNotFoundError()
        if record.object_key:
            self._storage.delete_pdf(principal_id, record.object_key)
        self._repository.delete_owned_document(document_id, principal_id)

    def get_conversation_documents(
        self, *, conversation_id: str, principal_id: str
    ) -> ConversationLiteratureDocumentsResponse:
        """校验会话归属后恢复该文献会话当前关联的文献。"""
        records = self._repository.get_conversation_documents(
            conversation_id, principal_id
        )
        if records is None:
            raise ConversationAccessDeniedError()
        return ConversationLiteratureDocumentsResponse(
            document_ids=[item.document_id for item in records],
            documents=[_to_summary(item) for item in records],
        )

    def update_conversation_documents(
        self, *, conversation_id: str, document_ids: list[str], principal_id: str
    ) -> ConversationLiteratureDocumentsResponse:
        """校验文献状态和所有权后原子更新历史会话文献关联。"""
        if len(document_ids) > LITERATURE_AGENT_MAX_DOCUMENTS:
            raise LiteratureDocumentNotReadyError()
        if document_ids:
            self._repository.get_owned_ready_documents(document_ids, principal_id)
        self._repository.set_conversation_documents(
            conversation_id, document_ids, principal_id
        )
        return self.get_conversation_documents(
            conversation_id=conversation_id,
            principal_id=principal_id,
        )

    def stream_chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        document_ids: list[str] | None,
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """验证文献范围后启动图，并在新会话首个运行事件前保存文献关联。\n\n        Step 1: 从请求或既有会话解析文献范围，并验证主体与 ready 状态。\n        Step 2: 将受控 document_ids 作为 graph_context 传入 LangGraph。\n        Step 3: 新会话创建后先保存文献关系，再向 SSE 发布运行事件。\n        """
        is_new_conversation = conversation_id is None
        if document_ids is None:
            if conversation_id is None:
                raise LiteratureDocumentNotReadyError()
            stored_ids = self._repository.get_conversation_document_ids(
                conversation_id, principal_id
            )
            if stored_ids is None:
                raise ConversationAccessDeniedError()
            if not stored_ids:
                raise LiteratureDocumentNotReadyError()
            resolved_document_ids = stored_ids
        else:
            if not document_ids or len(document_ids) > LITERATURE_AGENT_MAX_DOCUMENTS:
                raise LiteratureDocumentNotReadyError()
            resolved_document_ids = list(dict.fromkeys(document_ids))
            if len(resolved_document_ids) != len(document_ids):
                raise LiteratureDocumentNotReadyError()

        self._repository.get_owned_ready_documents(resolved_document_ids, principal_id)
        if conversation_id is not None and document_ids is not None:
            self._repository.set_conversation_documents(
                conversation_id, resolved_document_ids, principal_id
            )

        events = self._chat_service.stream_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
            graph_context={"document_ids": resolved_document_ids},
        )

        async def persist_new_conversation_scope() -> AsyncIterator[AgentEvent]:
            """在 RUN_STARTED 对外发送前保存新会话的文献选择。"""
            async for event in events:
                if is_new_conversation and event.event_type == AgentEventType.RUN_STARTED:
                    await asyncio.to_thread(
                        self._repository.set_conversation_documents,
                        event.conversation_id,
                        resolved_document_ids,
                        principal_id,
                    )
                yield event

        return persist_new_conversation_scope()


def _to_summary(record: LiteratureDocumentRecord) -> LiteratureDocumentSummary:
    """将内部文献记录映射为不含主体和 OSS 键的公开响应。"""
    return LiteratureDocumentSummary(
        document_id=record.document_id,
        title=record.title,
        source_type=record.source_type,
        source_url=record.source_url,
        file_name=record.file_name,
        status=record.status,
        error_code=record.error_code,
        error_message=record.error_message,
        page_count=record.page_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _safe_file_name(file_name: str) -> str:
    """去除路径、控制字符并固定扩展名，避免用户输入成为 OSS 路径。"""
    leaf_name = file_name.replace("\\", "/").split("/")[-1]
    visible_name = _SAFE_FILE_NAME_PATTERN.sub("", leaf_name).strip()[:180]
    if not visible_name:
        visible_name = "literature.pdf"
    stem, separator, extension = visible_name.rpartition(".")
    if separator and extension.lower() == "pdf":
        return f"{stem[:170]}.pdf"
    return f"{visible_name[:175]}.pdf"
