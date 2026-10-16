"""Celery PDF 文献导入任务，负责解析、向量化和状态更新。"""

from __future__ import annotations

import hashlib
import logging

from celery import Task

from agents.labor_law_agent.constants import LEGAL_EMBEDDING_DIMENSIONS
from agents.literature_reader_agent.chunker import chunk_segments
from agents.literature_reader_agent.constants import (
    DOCUMENT_STATUS_FAILED,
    DOCUMENT_STATUS_PROCESSING,
    DOCUMENT_STATUS_READY,
)
from agents.literature_reader_agent.document_parser import LiteratureParseError, parse_pdf
from agents.literature_reader_agent.embedding import create_literature_embedding_model
from agents.literature_reader_agent.schemas import LiteratureDocumentRecord
from app.crud.literature import PostgresLiteratureRepository
from app.db.database import PostgresDatabase
from infra.celery_app import celery_app
from infra.literature_document_storage import (
    AliyunOSSLiteratureStorage,
    LiteratureStorageError,
    UnavailableLiteratureStorage,
)
from infra.settings import AppSettings
from infra.snowflake import get_snowflake_generator


logger = logging.getLogger(__name__)
_TASK_NAME = "app.service.literature_tasks.process_literature_document"
_FAILURE_INGESTION = ("INGESTION_FAILED", "文献处理失败，请确认文件可读取后重新导入。")
_FAILURE_EMBEDDING = ("EMBEDDING_UNAVAILABLE", "文献向量服务未配置或暂时不可用。")


@celery_app.task(bind=True, name=_TASK_NAME, acks_late=True)
def process_literature_document(_task: Task, document_id: str) -> None:
    """处理单篇 queued PDF 文献并更新入库状态。"""
    settings = AppSettings()
    if settings.database_url is None:
        logger.error("文献处理缺少数据库配置 document_id=%s", document_id)
        return

    worker_id = settings.literature_worker_snowflake_id
    with PostgresDatabase(
        settings.database_url,
        id_generator=get_snowflake_generator(worker_id),
    ) as database:
        repository = PostgresLiteratureRepository(database)
        record = repository.get_document_for_task(document_id)
        if record is None or record.status == DOCUMENT_STATUS_READY:
            return

        repository.update_status(document_id, DOCUMENT_STATUS_PROCESSING)
        try:
            _process_document(settings, repository, record)
        except LiteratureParseError as error:
            _mark_failed(
                repository,
                document_id,
                ("DOCUMENT_PARSE_FAILED", str(error)),
            )
        except LiteratureStorageError:
            _mark_failed(
                repository,
                document_id,
                ("DOCUMENT_STORAGE_FAILED", "文献原件暂时无法读取或保存。"),
            )
        except Exception as error:
            logger.warning(
                "文献处理失败 document_id=%s error_type=%s",
                document_id,
                type(error).__name__,
            )
            if isinstance(error, EmbeddingServiceUnavailable):
                _mark_failed(repository, document_id, _FAILURE_EMBEDDING)
            else:
                _mark_failed(repository, document_id, _FAILURE_INGESTION)


def _process_document(
    settings: AppSettings,
    repository: PostgresLiteratureRepository,
    record: LiteratureDocumentRecord,
) -> None:
    """解析单篇文献、生成定长向量并原子写入可检索分块。"""
    storage = (
        AliyunOSSLiteratureStorage(settings)
        if settings.aliyun_oss_configured
        else UnavailableLiteratureStorage()
    )
    if record.object_key is None:
        raise LiteratureParseError("文献没有可读取的 PDF 原件，请重新上传 PDF 文件")
    source_type = record.source_type
    source_bytes = storage.read_pdf(record.owner_principal, record.object_key)
    object_key = record.object_key
    parsed = parse_pdf(
        source_bytes,
        fallback_title=record.title,
        max_pages=settings.literature_max_pages,
    )
    content_type = parsed.content_type

    chunks = chunk_segments(
        parsed.segments,
        max_chars=settings.literature_chunk_max_chars,
    )
    if not chunks:
        raise LiteratureParseError("文献正文未能切分为有效段落")

    embedding_model = create_literature_embedding_model(settings)
    if embedding_model is None:
        raise EmbeddingServiceUnavailable()
    try:
        vectors = embedding_model.embed_documents([chunk.content for chunk in chunks])
    except Exception as error:
        raise EmbeddingServiceUnavailable() from error
    if len(vectors) != len(chunks) or any(
        len(vector) != LEGAL_EMBEDDING_DIMENSIONS for vector in vectors
    ):
        raise EmbeddingServiceUnavailable()

    from agents.literature_reader_agent.schemas import EmbeddedLiteratureChunk

    embedded_chunks = [
        EmbeddedLiteratureChunk(chunk=chunk, embedding=vector)
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    repository.complete_ingestion(
        record.document_id,
        title=parsed.title or record.title,
        source_type=source_type,
        content_type=content_type,
        file_size=len(source_bytes),
        content_sha256=hashlib.sha256(source_bytes).hexdigest(),
        page_count=parsed.page_count,
        object_key=object_key,
        chunks=embedded_chunks,
    )


def _mark_failed(
    repository: PostgresLiteratureRepository,
    document_id: str,
    failure: tuple[str, str],
) -> None:
    """写入面向用户的稳定失败代码和安全错误说明。"""
    repository.update_status(
        document_id,
        DOCUMENT_STATUS_FAILED,
        error_code=failure[0],
        error_message=failure[1],
    )


class EmbeddingServiceUnavailable(RuntimeError):
    """Embedding 未配置、返回维度错误或生成失败。"""

