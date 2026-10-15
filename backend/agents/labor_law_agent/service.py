"""编排法规文件校验、条文解析、Embedding 生成和知识库版本写入。"""

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from langchain_openai import OpenAIEmbeddings

from agents.labor_law_agent.constants import (
    LEGAL_CORPUS_DIR,
    LEGAL_CORPUS_MANIFEST_NAME,
    LEGAL_CORPUS_SOURCE_DIR,
    LEGAL_EMBEDDING_DIMENSIONS,
    LEGAL_STATUS_EFFECTIVE,
)
from agents.labor_law_agent.document_parser import extract_document_text, parse_articles
from agents.labor_law_agent.repository import LegalKnowledgeRepository
from agents.labor_law_agent.schemas import EmbeddedArticle, ParsedArticle, ParsedLegalDocument

logger = logging.getLogger(__name__)


class LegalKnowledgeService:
    """法律知识库导入服务，按版本哈希保证重复导入可重试。"""

    def __init__(
        self,
        repository: LegalKnowledgeRepository,
        embedding_model: OpenAIEmbeddings,
        agent_directory: Path | None = None,
    ) -> None:
        """注入向量模型和 PostgreSQL 仓储适配器。"""
        self._repository = repository
        self._embedding_model = embedding_model
        self._agent_directory = agent_directory or Path(__file__).resolve().parent

    def import_manifest(self) -> int:
        """逐部校验并导入 manifest 中的现行法规版本。"""
        # Step 1: 读取智能体目录内的来源清单，限制文件路径只能位于 source 目录。
        corpus_directory = self._agent_directory / LEGAL_CORPUS_DIR
        source_directory = (self._agent_directory / LEGAL_CORPUS_SOURCE_DIR).resolve()
        manifest_path = corpus_directory / LEGAL_CORPUS_MANIFEST_NAME
        records = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
        if not isinstance(records, list) or not records:
            raise ValueError("法规来源清单必须是非空 JSON 数组")

        # Step 2: 解析条文并为整部法规的条文批量生成 Embedding。
        imported_count = 0
        active_titles: set[str] = set()
        for record in records:
            document, parsed_articles = self._parse_manifest_record(record, source_directory)
            vectors = self._embedding_model.embed_documents(
                [article.content for article in parsed_articles]
            )
            if len(vectors) != len(parsed_articles):
                raise RuntimeError(f"Embedding 返回数量不匹配：{document.title}")
            embedded_articles = []
            for article, vector in zip(parsed_articles, vectors, strict=True):
                if len(vector) != LEGAL_EMBEDDING_DIMENSIONS:
                    raise ValueError(
                        f"Embedding 维度应为 {LEGAL_EMBEDDING_DIMENSIONS}，实际为 {len(vector)}"
                    )
                embedded_articles.append(EmbeddedArticle(article=article, embedding=vector))

            # Step 3: 仓储在同一数据库事务内保存版本和法条；内容摘要相同则更新原版本。
            self._repository.upsert_law_version(document, embedded_articles)
            active_titles.add(document.title)
            imported_count += 1
            logger.info(
                "法律法规导入完成 title=%s article_count=%s sha256=%s",
                document.title,
                len(parsed_articles),
                document.source_sha256,
            )
        # Step 4: 官方清单中已不存在的法规退出检索，历史版本仍保留。
        self._repository.deactivate_missing_laws(active_titles)
        return imported_count

    def _parse_manifest_record(
        self,
        record: Any,
        source_directory: Path,
    ) -> tuple[ParsedLegalDocument, list[ParsedArticle]]:
        """校验 manifest 元数据、文件摘要和法条识别结果。"""
        if not isinstance(record, dict):
            raise ValueError("法规来源清单中的每项必须是对象")
        file_name = _required_string(record, "file")
        source_path = (source_directory / file_name).resolve()
        if not source_path.is_relative_to(source_directory) or not source_path.is_file():
            raise ValueError(f"法规源文件路径无效或文件不存在：{file_name}")
        file_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        expected_digest = _required_string(record, "sha256")
        if file_digest != expected_digest:
            raise ValueError(f"法规源文件摘要与 manifest 不一致：{file_name}")

        title = _required_string(record, "title")
        parsed_articles = parse_articles(extract_document_text(source_path))
        original_file = record.get("original_file")
        original_digest = record.get("original_sha256")
        if original_file is not None and not isinstance(original_file, str):
            raise ValueError(f"法规原始文件名称无效：{file_name}")
        if original_digest is not None and not isinstance(original_digest, str):
            raise ValueError(f"法规原始文件摘要无效：{file_name}")
        if original_file:
            original_path = (source_directory / original_file).resolve()
            if not original_path.is_relative_to(source_directory) or not original_path.is_file():
                raise ValueError(f"法规官方原始文件路径无效或文件不存在：{original_file}")
            actual_original_digest = hashlib.sha256(original_path.read_bytes()).hexdigest()
            if original_digest and actual_original_digest != original_digest:
                raise ValueError(f"法规官方原始文件摘要与 manifest 不一致：{original_file}")
            original_digest = actual_original_digest
        document = ParsedLegalDocument(
            title=title,
            legal_type=_required_string(record, "legal_type"),
            issuer=_required_string(record, "issuer"),
            source_file=f"{LEGAL_CORPUS_SOURCE_DIR}/{file_name}",
            original_file=(
                f"{LEGAL_CORPUS_SOURCE_DIR}/{original_file}" if original_file else None
            ),
            source_sha256=file_digest,
            original_sha256=original_digest,
            source_url=_required_string(record, "source_url"),
            promulgated_on=_optional_string(record, "promulgated_on"),
            effective_on=_optional_string(record, "effective_on"),
            retrieved_on=_required_string(record, "retrieved_on"),
            status=_required_string(record, "status"),
            articles=parsed_articles,
        )
        if document.status != LEGAL_STATUS_EFFECTIVE:
            raise ValueError(f"仅允许导入现行有效法规：{title}")
        return document, parsed_articles


def _required_string(record: dict[str, Any], key: str) -> str:
    """读取清单中必需的非空字符串字段。"""
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"法规来源清单缺少有效字段：{key}")
    return value.strip()


def _optional_string(record: dict[str, Any], key: str) -> str | None:
    """读取可空字符串元数据字段。"""
    value = record.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"法规来源清单字段格式错误：{key}")
    return value.strip() or None

