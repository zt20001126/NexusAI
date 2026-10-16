"""限定所选文献执行关键词与向量混合检索并判断证据覆盖。"""

from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict

from langchain_openai import OpenAIEmbeddings

from agents.literature_reader_agent.constants import (
    LITERATURE_DEFAULT_KEYWORD_LIMIT,
    LITERATURE_DEFAULT_SUMMARY_CHUNK_COUNT,
    LITERATURE_MIN_KEYWORD_MATCHES,
    LITERATURE_RRF_K,
)
from agents.literature_reader_agent.schemas import (
    LiteratureEvidence,
    LiteratureRetrievalResult,
)
from agents.literature_reader_agent.repository import LiteratureRepository


logger = logging.getLogger(__name__)
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u3400-\u9fff]+")
_STOP_WORDS = frozenset(
    {
        "请问", "请教", "如何", "为什么", "什么", "哪些", "是否", "可以", "能够",
        "进行", "分析", "研究", "文献", "论文", "作者", "结果", "结论", "方法",
        "总结", "对比", "比较", "综述", "please", "what", "which", "does", "this",
        "that", "with", "from", "about", "study", "paper", "article",
    }
)
_TASK_PATTERNS = (
    ("comparison", re.compile(r"比较|对比|异同|相比|差异|共同点|compare|contrast", re.I)),
    ("methods", re.compile(r"研究方法|方法梳理|实验设计|研究设计|方法部分|methodology|methods?", re.I)),
    ("summary", re.compile(r"总结|概括|梳理全文|解读全文|主要内容|核心内容|全文概览|summary|summari[sz]e|overview", re.I)),
)


class LiteratureRetrievalService:
    """为每篇所选文献执行有界混合检索并计算检索充分性。"""

    def __init__(
        self,
        repository: LiteratureRepository,
        embedding_model: OpenAIEmbeddings | None,
        *,
        top_k: int,
        candidate_count: int,
        min_similarity: float,
        context_max_chars: int,
        chunk_max_chars: int,
    ) -> None:
        """注入文献仓储、Embedding 和检索资源边界。"""
        self._repository = repository
        self._embedding_model = embedding_model
        self._top_k = top_k
        self._candidate_count = candidate_count
        self._min_similarity = min_similarity
        self._context_max_chars = context_max_chars
        self._chunk_max_chars = chunk_max_chars

    async def retrieve(
        self,
        query: str,
        document_ids: list[str],
        principal_id: str,
    ) -> tuple[str, LiteratureRetrievalResult]:
        """分类任务、逐篇检索，比较任务要求每篇文献均有足够依据。"""
        task_type = classify_literature_request(query)
        terms = extract_keyword_terms(query)[:LITERATURE_DEFAULT_KEYWORD_LIMIT]
        summary_chunks_per_document = min(
            LITERATURE_DEFAULT_SUMMARY_CHUNK_COUNT,
            max(
                1,
                self._context_max_chars
                // max(1, len(document_ids))
                // self._chunk_max_chars,
            ),
        )

        # Step 1: 查询向量只生成一次，之后每篇文献分别执行主体限定的检索。
        query_embedding: list[float] | None = None
        if self._embedding_model is not None and task_type != "summary":
            try:
                query_embedding = await self._embedding_model.aembed_query(query[:4_000])
            except Exception as error:
                logger.warning("文献查询向量生成失败 error_type=%s", type(error).__name__)

        # Step 2: 每篇文献独立判断覆盖，防止比较回答只引用其中一篇。
        per_document = await asyncio.gather(
            *(
                self._retrieve_one_document(
                    terms=terms,
                    document_id=document_id,
                    principal_id=principal_id,
                    query_embedding=query_embedding,
                    task_type=task_type,
                    summary_chunk_limit=summary_chunks_per_document,
                )
                for document_id in document_ids
            )
        )
        evidence: list[LiteratureEvidence] = []
        sufficient_document_ids: set[str] = set()
        for document_id, document_evidence, is_sufficient in per_document:
            if is_sufficient:
                sufficient_document_ids.add(document_id)
            evidence.extend(document_evidence)

        return task_type, LiteratureRetrievalResult(
            evidence=_limit_context(evidence, document_ids, self._context_max_chars),
            sufficient_document_ids=frozenset(sufficient_document_ids),
        )

    async def _retrieve_one_document(
        self,
        *,
        terms: list[str],
        document_id: str,
        principal_id: str,
        query_embedding: list[float] | None,
        task_type: str,
        summary_chunk_limit: int,
    ) -> tuple[str, list[LiteratureEvidence], bool]:
        """在线程池中执行单篇文献的关键词和 pgvector 查询。"""
        if task_type == "summary":
            outline = await asyncio.to_thread(
                self._repository.get_document_outline,
                document_id,
                principal_id,
                summary_chunk_limit,
            )
            return document_id, outline, bool(outline)

        keyword_task = asyncio.to_thread(
            self._repository.search_keywords,
            terms,
            [document_id],
            principal_id,
            self._candidate_count,
        )
        if query_embedding is None:
            keyword_matches = await keyword_task
            vector_matches: list[LiteratureEvidence] = []
        else:
            vector_task = asyncio.to_thread(
                self._repository.search_vectors,
                query_embedding,
                [document_id],
                principal_id,
                self._candidate_count,
            )
            keyword_matches, vector_matches = await asyncio.gather(
                keyword_task,
                vector_task,
            )

        ranked = _fuse_rankings(keyword_matches, vector_matches, self._top_k)
        vector_supported = any(
            item.vector_similarity >= self._min_similarity for item in ranked
        )
        keyword_supported = any(
            item.keyword_matches >= LITERATURE_MIN_KEYWORD_MATCHES for item in ranked
        )
        return document_id, ranked, vector_supported or keyword_supported

    @staticmethod
    def task_requires_all_documents(task_type: str) -> bool:
        """总结和比较任务需要所选集合中的每篇文献都有足够证据。"""
        return task_type in {"comparison", "summary"}




def classify_literature_request(query: str) -> str:
    """将用户请求归入问答、总结、方法梳理或比较四类处理意图。"""
    for task_type, pattern in _TASK_PATTERNS:
        if pattern.search(query):
            return task_type
    return "question"


def extract_keyword_terms(query: str) -> list[str]:
    """从中英文问题提取关键词，并用相邻双字扩展中文长词。"""
    terms: list[str] = []
    for token in _TOKEN_PATTERN.findall(query):
        if token.lower() in _STOP_WORDS:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            if len(token) <= 4:
                terms.append(token)
            else:
                terms.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            terms.append(token)
    return list(dict.fromkeys(term for term in terms if term.lower() not in _STOP_WORDS))


def _fuse_rankings(
    keyword_matches: list[LiteratureEvidence],
    vector_matches: list[LiteratureEvidence],
    top_k: int,
) -> list[LiteratureEvidence]:
    """使用 RRF 融合关键词与向量排名并保留两路分数。"""
    records: dict[str, LiteratureEvidence] = {}
    score_by_id: dict[str, float] = defaultdict(float)
    for matches in (keyword_matches, vector_matches):
        for rank, item in enumerate(matches, start=1):
            records[item.evidence_id] = _merge_evidence(
                records.get(item.evidence_id),
                item,
            )
            score_by_id[item.evidence_id] += 1 / (LITERATURE_RRF_K + rank)
    return sorted(
        records.values(),
        key=lambda item: score_by_id[item.evidence_id],
        reverse=True,
    )[:top_k]


def _merge_evidence(
    current: LiteratureEvidence | None,
    incoming: LiteratureEvidence,
) -> LiteratureEvidence:
    """合并相同分块的关键词和向量命中分数。"""
    if current is None:
        return incoming
    return LiteratureEvidence(
        evidence_id=current.evidence_id,
        document_id=current.document_id,
        title=current.title,
        source_type=current.source_type,
        source_url=current.source_url,
        chapter=current.chapter,
        section=current.section,
        page_start=current.page_start,
        page_end=current.page_end,
        paragraph_start=current.paragraph_start,
        paragraph_end=current.paragraph_end,
        content=current.content,
        vector_similarity=max(current.vector_similarity, incoming.vector_similarity),
        keyword_matches=max(current.keyword_matches, incoming.keyword_matches),
    )


def _limit_context(
    evidence: list[LiteratureEvidence],
    document_ids: list[str],
    max_chars: int,
) -> list[LiteratureEvidence]:
    """按文献轮转保留高分证据，确保多篇比较不会挤掉某篇来源。"""
    grouped: dict[str, list[LiteratureEvidence]] = {
        document_id: [] for document_id in document_ids
    }
    for item in evidence:
        grouped.setdefault(item.document_id, []).append(item)

    result: list[LiteratureEvidence] = []
    used_chars = 0
    rank = 0
    while True:
        added_any = False
        for document_id in document_ids:
            items = grouped.get(document_id, [])
            if rank >= len(items):
                continue
            item = items[rank]
            item_size = len(item.content)
            if used_chars + item_size > max_chars:
                continue
            result.append(item)
            used_chars += item_size
            added_any = True
        if not added_any:
            break
        rank += 1
    return result

