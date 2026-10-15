"""执行法条号、关键词和向量混合检索及确定性重排序。"""

import asyncio
from dataclasses import dataclass
import logging
import re

from langchain_openai import OpenAIEmbeddings

from agents.labor_law_agent.constants import (
    LEGAL_DEFAULT_KEYWORD_LIMIT,
    LEGAL_MIN_KEYWORD_MATCHES,
    LEGAL_RRF_K,
)
from agents.labor_law_agent.repository import LegalKnowledgeRepository
from agents.labor_law_agent.schemas import LegalEvidence

_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[\u3400-\u9fff]+")
logger = logging.getLogger(__name__)
_ARTICLE_REFERENCE_PATTERN = re.compile(
    r"第(?P<number>[0-9]{1,4}|[零〇一二三四五六七八九十百千]+)条"
    r"(?:之(?P<subnumber>[0-9]+|[一二三四五六七八九十]+))?"
)
_CHINESE_DIGITS = "零一二三四五六七八九"
_STOP_WORDS = frozenset(
    {
        "请问",
        "请教",
        "怎么",
        "怎么办",
        "如何",
        "是否",
        "可以",
        "规定",
        "法律",
        "法规",
        "条文",
        "员工",
        "劳动者",
        "用人单位",
    }
)


@dataclass(frozen=True)
class LegalRetrievalResult:
    """融合重排序后的证据和检索充分性判断。"""

    evidence: list[LegalEvidence]
    sufficient: bool


class LegalRetrievalService:
    """组合关键词检索、pgvector 向量检索和倒数排序融合。"""

    def __init__(
        self,
        repository: LegalKnowledgeRepository,
        embedding_model: OpenAIEmbeddings | None,
        top_k: int,
        candidate_count: int,
        min_similarity: float,
    ) -> None:
        """注入持久化、Embedding 和召回边界配置。"""
        self._repository = repository
        self._embedding_model = embedding_model
        self._top_k = top_k
        self._candidate_count = candidate_count
        self._min_similarity = min_similarity

    async def retrieve(self, query: str) -> LegalRetrievalResult:
        """并行查询词项与向量索引，再融合排序并判断是否达到回答门槛。"""
        normalized_query = query.strip()[:4_000]
        terms = extract_keyword_terms(normalized_query)
        article_no = extract_article_reference(normalized_query)

        # Step 1: 关键词与精确条号查询走线程池，避免同步 SQL 阻塞异步图节点。
        keyword_task = asyncio.to_thread(
            self._repository.search_keywords,
            terms[:LEGAL_DEFAULT_KEYWORD_LIMIT],
            article_no,
            self._candidate_count,
        )
        vector_task = self._search_vectors(normalized_query)
        keyword_matches, vector_matches = await asyncio.gather(keyword_task, vector_task)

        # Step 2: 通过 Reciprocal Rank Fusion 合并两路结果，再对相似度和词项命中数重排。
        ranked = _fuse_and_rerank(
            keyword_matches,
            vector_matches,
            article_no,
            self._top_k,
        )
        vector_supported = any(
            item.vector_similarity >= self._min_similarity for item in ranked
        )
        keyword_supported = any(
            item.keyword_matches >= LEGAL_MIN_KEYWORD_MATCHES for item in ranked
        )
        exact_article_supported = article_no is not None and any(
            item.article_no == article_no for item in ranked
        )
        return LegalRetrievalResult(
            evidence=ranked,
            sufficient=vector_supported or keyword_supported or exact_article_supported,
        )

    async def _search_vectors(self, query: str) -> list[LegalEvidence]:
        """在向量模型配置后异步生成查询向量，并将同步数据库查询移出事件循环。"""
        if self._embedding_model is None:
            return []
        try:
            embedding = await self._embedding_model.aembed_query(query)
            return await asyncio.to_thread(
                self._repository.search_vectors,
                embedding,
                self._candidate_count,
            )
        except Exception as exc:
            # Embedding 服务暂时不可用时仍保留关键词检索结果，不让其阻断另一条召回路径。
            logger.warning("劳动法律向量检索失败 error_type=%s", type(exc).__name__)
            return []


def extract_keyword_terms(query: str) -> list[str]:
    """生成中英文检索词，中文长词采用相邻双字覆盖以改善关键词召回。"""
    terms: list[str] = []
    for token in _TOKEN_PATTERN.findall(query):
        if token in _STOP_WORDS:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", token):
            if len(token) <= 4:
                terms.append(token)
            else:
                terms.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            terms.append(token)
    return list(dict.fromkeys(term for term in terms if term not in _STOP_WORDS))


def extract_article_reference(query: str) -> str | None:
    """识别中文或阿拉伯数字法条号并规范为法规原文的中文编号。"""
    match = _ARTICLE_REFERENCE_PATTERN.search(query)
    if match is None:
        return None
    raw_number = match.group("number")
    number = int(raw_number) if raw_number.isdigit() else _parse_chinese_number(raw_number)
    article_no = f"第{_to_chinese_number(number)}条"
    subnumber = match.group("subnumber")
    if subnumber:
        parsed_subnumber = int(subnumber) if subnumber.isdigit() else _parse_chinese_number(subnumber)
        article_no += f"之{_to_chinese_number(parsed_subnumber)}"
    return article_no


def _parse_chinese_number(value: str) -> int:
    """把常用法条中文数字解析为整数。"""
    digit_values = {char: index for index, char in enumerate(_CHINESE_DIGITS)}
    digit_values["〇"] = 0
    units = {"十": 10, "百": 100, "千": 1_000}
    total = 0
    pending_digit = 0
    for char in value:
        if char in digit_values:
            pending_digit = digit_values[char]
        elif char in units:
            unit = units[char]
            total += (pending_digit or (1 if unit == 10 else 0)) * unit
            pending_digit = 0
    return total + pending_digit


def _to_chinese_number(value: int) -> str:
    """把法规条号常见的 1 至 9999 数字转换为中文序数。"""
    if value <= 0 or value >= 10_000:
        return str(value)
    digits = "零一二三四五六七八九"
    units = ("", "十", "百", "千")
    raw = str(value)
    pieces: list[str] = []
    zero_pending = False
    for position, digit_char in enumerate(reversed(raw)):
        digit = int(digit_char)
        if digit == 0:
            if pieces:
                zero_pending = True
            continue
        if zero_pending:
            pieces.append("零")
            zero_pending = False
        number_text = digits[digit]
        if position == 1 and digit == 1 and len(raw) <= 2:
            number_text = ""
        pieces.append(number_text + units[position])
    return "".join(reversed(pieces))


def _fuse_and_rerank(
    keyword_matches: list[LegalEvidence],
    vector_matches: list[LegalEvidence],
    article_no: str | None,
    top_k: int,
) -> list[LegalEvidence]:
    """按双路倒数排名融合并使用原始命中分数进行第二阶段重排。"""
    merged: dict[str, LegalEvidence] = {}
    fused_scores: dict[str, float] = {}
    for rank, evidence in enumerate(keyword_matches, start=1):
        merged[evidence.article_id] = evidence
        fused_scores[evidence.article_id] = fused_scores.get(evidence.article_id, 0.0) + 1.0 / (
            LEGAL_RRF_K + rank
        )
    for rank, evidence in enumerate(vector_matches, start=1):
        previous = merged.get(evidence.article_id)
        merged[evidence.article_id] = (
            LegalEvidence(
                article_id=evidence.article_id,
                title=evidence.title,
                article_no=evidence.article_no,
                chapter=evidence.chapter,
                section=evidence.section,
                content=evidence.content,
                source_url=evidence.source_url,
                effective_on=evidence.effective_on,
                vector_similarity=evidence.vector_similarity,
                keyword_matches=previous.keyword_matches if previous else 0,
            )
        )
        fused_scores[evidence.article_id] = fused_scores.get(evidence.article_id, 0.0) + 1.0 / (
            LEGAL_RRF_K + rank
        )

    ranked = sorted(
        merged.values(),
        key=lambda item: (
            fused_scores[item.article_id]
            + item.vector_similarity * 0.01
            + min(item.keyword_matches, 10) * 0.001
            + (0.1 if item.article_no == article_no else 0.0),
            item.vector_similarity,
            item.keyword_matches,
        ),
        reverse=True,
    )
    return ranked[:top_k]

