"""文献导入、位置保留和证据约束回答测试。"""

import json
from dataclasses import replace
from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import PrivateAttr, ValidationError

from agents.literature_reader_agent.chunker import chunk_segments
from agents.literature_reader_agent.chunker import sample_evenly
from agents.literature_reader_agent.constants import (
    LITERATURE_ABSTENTION,
    LITERATURE_ANSWER_MAX_CLAIMS,
)
from agents.literature_reader_agent.graph import build_literature_reader_agent_graph
from agents.literature_reader_agent.graph import _citation_marker
from agents.literature_reader_agent.prompts import LITERATURE_ANSWER_PROMPT
from agents.literature_reader_agent.retrieval import LiteratureRetrievalService
from agents.literature_reader_agent.schemas import (
    LiteratureAnswerDraft,
    LiteratureEvidence,
    LiteratureRetrievalResult,
    ParsedSegment,
)


def test_answer_prompt_matches_claim_limit_and_requires_consolidation() -> None:
    """回答提示词需与结构上限一致，并要求压缩过多的候选要点。"""
    assert f"最多包含 {LITERATURE_ANSWER_MAX_CLAIMS} 条声明" in LITERATURE_ANSWER_PROMPT
    assert "合并同主题" in LITERATURE_ANSWER_PROMPT
    assert "不得按每个证据分块逐条生成声明" in LITERATURE_ANSWER_PROMPT


def test_chunker_preserves_pdf_location_when_splitting_long_paragraph() -> None:
    """超长文本切块后仍保留原有章节、页码和段落编号。"""
    chunks = chunk_segments(
        [
            ParsedSegment(
                content="abcdefghijk",
                chapter="第三章 研究结果",
                section="3.1 实验结果",
                page_number=12,
                paragraph_number=4,
            )
        ],
        max_chars=6,
    )

    assert [chunk.content for chunk in chunks] == ["abcdef", "ghijk"]
    assert all(chunk.page_start == chunk.page_end == 12 for chunk in chunks)
    assert all(chunk.paragraph_start == chunk.paragraph_end == 4 for chunk in chunks)
    assert all(chunk.chapter == "第三章 研究结果" for chunk in chunks)
    assert all(chunk.section == "3.1 实验结果" for chunk in chunks)


def test_summary_sampling_covers_start_and_end_of_long_document() -> None:
    """全文概览的代表性片段覆盖文献开头、结尾和中间部分。"""
    positions = sample_evenly(total_items=100, limit=5)

    assert positions[0] == 0
    assert positions[-1] == 99
    assert all(right > left for left, right in zip(positions, positions[1:]))


async def test_summary_retrieval_reads_document_outline_without_query_embedding() -> None:
    """总结请求使用跨文献顺序抽样，而不是只召回问题词相似的段落。"""
    repository = FakeOutlineRepository(_evidence())
    service = LiteratureRetrievalService(
        repository=repository,
        embedding_model=None,
        top_k=8,
        candidate_count=30,
        min_similarity=0.32,
        context_max_chars=24_000,
        chunk_max_chars=1_200,
    )

    task_type, result = await service.retrieve(
        "请总结这篇文献",
        ["1001"],
        "local-development",
    )

    assert task_type == "summary"
    assert repository.requested_limit == 16
    assert result.sufficient_document_ids == frozenset({"1001"})
    assert result.evidence[0].evidence_id == "9001"


def test_answer_schema_rejects_model_authored_unanswered_text() -> None:
    """回答中未覆盖的部分只能由服务端输出固定说明。"""
    with pytest.raises(ValidationError):
        LiteratureAnswerDraft.model_validate(
            {"claims": [], "unanswered_aspects": ["模型编写的未核实结论"]}
        )


class ScriptedChatModel(BaseChatModel):
    """按顺序返回草稿和支持关系核验结果的离线模型。"""

    responses: list[str]
    _response_index: int = PrivateAttr(default=0)

    @property
    def _llm_type(self) -> str:
        return "scripted-literature-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        del messages, stop, run_manager, kwargs
        content = self.responses[self._response_index]
        self._response_index += 1
        return ChatResult(generations=[ChatGeneration(message=AIMessage(content=content))])


class FakeRetrievalService:
    """返回预定义证据，隔离图路由测试与数据库和 Embedding。"""

    def __init__(
        self,
        evidence: list[LiteratureEvidence],
        task_type: str,
    ) -> None:
        self._evidence = evidence
        self._task_type = task_type

    async def retrieve(
        self,
        query: str,
        document_ids: list[str],
        principal_id: str,
    ) -> tuple[str, LiteratureRetrievalResult]:
        del query, document_ids, principal_id
        return self._task_type, LiteratureRetrievalResult(
            evidence=self._evidence,
            sufficient_document_ids=frozenset(
                item.document_id for item in self._evidence
            ),
        )

    @staticmethod
    def task_requires_all_documents(task_type: str) -> bool:
        return task_type in {"comparison", "summary"}


class FakeOutlineRepository:
    """记录文献概览检索参数并返回代表性证据。"""

    def __init__(self, evidence: LiteratureEvidence) -> None:
        self.evidence = evidence
        self.requested_limit: int | None = None

    def get_document_outline(
        self, document_id: str, principal_id: str, limit: int
    ) -> list[LiteratureEvidence]:
        del document_id, principal_id
        self.requested_limit = limit
        return [self.evidence]


class FakeLiteratureRepository:
    """只返回图测试中预先定义且被选择的证据。"""

    def __init__(self, evidence: list[LiteratureEvidence]) -> None:
        self._evidence = evidence

    def get_evidence_by_ids(
        self,
        evidence_ids: list[str],
        document_ids: list[str],
        principal_id: str,
    ) -> list[LiteratureEvidence]:
        del principal_id
        return [
            item
            for item in self._evidence
            if item.evidence_id in evidence_ids and item.document_id in document_ids
        ]


def _evidence() -> LiteratureEvidence:
    return LiteratureEvidence(
        evidence_id="9001",
        document_id="1001",
        title="研究论文",
        source_type="pdf_upload",
        source_url=None,
        chapter="第三章 研究结果",
        section="3.1 实验结果",
        page_start=12,
        page_end=12,
        paragraph_start=4,
        paragraph_end=4,
        content="实验组的平均值高于对照组。",
    )


def test_citation_escapes_document_metadata_before_markdown_rendering() -> None:
    """服务端生成引用时转义来源标题并编码链接括号。"""
    evidence = replace(
        _evidence(),
        title="paper](https://evil.example)",
        source_url="https://example.org/paper(a).pdf?x=1&y=2",
    )

    marker = _citation_marker(evidence)

    assert r"paper\]" in marker
    assert r"\(https://evil\.example\)" in marker
    assert "paper%28a%29.pdf" in marker


async def _run_graph(
    responses: list[str],
    *,
    task_type: str = "question",
    evidence_count: int = 1,
    source_type: str = "pdf_upload",
    source_url: str | None = None,
) -> str:
    """运行文献图并返回最终助手文本。"""
    first_evidence = _evidence()
    if source_type == "web_url":
        first_evidence = replace(
            first_evidence,
            source_type=source_type,
            source_url=source_url,
            chapter="HTML Heading",
            section="HTML Subheading",
            page_start=None,
            page_end=None,
            paragraph_start=None,
            paragraph_end=None,
        )
    evidence = [first_evidence]
    if evidence_count > 1:
        evidence.extend(
            replace(
                _evidence(),
                evidence_id="9002",
                document_id="1002",
                title="第二篇研究论文",
            )
            for _ in range(evidence_count - 1)
        )
    graph = build_literature_reader_agent_graph(
        checkpointer=None,
        chat_model=ScriptedChatModel(responses=responses),
        retrieval_service=FakeRetrievalService(evidence, task_type),
        repository=FakeLiteratureRepository(evidence),
    )
    result = await graph.ainvoke(
        {
            "messages": [HumanMessage(content="实验结果是什么？")],
            "original_request": "实验结果是什么？",
            "principal_id": "local-development",
            "document_ids": [item.document_id for item in evidence],
        }
    )
    return str(result["messages"][-1].content)


async def test_graph_renders_only_server_generated_pdf_citations() -> None:
    """图只在声明通过支持核验后回答，并从证据元数据生成引用。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"实验组的平均值高于对照组。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ]
    )

    assert "实验组的平均值高于对照组。" in answer
    assert "第 12 页" in answer
    assert "第 4 段" in answer
    assert "实验组的平均值高于对照组。" in answer


async def test_graph_retries_answer_when_evidence_quote_exceeds_schema_limit() -> None:
    """摘录超长时将校验错误反馈给模型重生成，而非直接中断本轮回答。"""
    invalid_draft = json.dumps(
        {
            "claims": [
                {
                    "text": "实验组的平均值高于对照组。",
                    "evidence_quotes": [
                        {"evidence_id": "9001", "quote": "x" * 501}
                    ],
                }
            ]
        }
    )
    valid_draft = json.dumps(
        {
            "claims": [
                {
                    "text": "实验组的平均值高于对照组。",
                    "evidence_quotes": [
                        {
                            "evidence_id": "9001",
                            "quote": "实验组的平均值高于对照组。",
                        }
                    ],
                }
            ]
        },
        ensure_ascii=False,
    )
    answer = await _run_graph(
        [
            invalid_draft,
            valid_draft,
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ]
    )

    assert "实验组的平均值高于对照组。" in answer


async def test_graph_shows_web_source_without_inventing_page_or_paragraph() -> None:
    """网页引文显示可追溯来源标题和链接，不添加 PDF 位置标注。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"实验组的平均值高于对照组。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ],
        source_type="web_url",
        source_url="https://example.org/paper",
    )

    assert "《研究论文》" in answer
    assert "https://example.org/paper" in answer
    assert "第 12 页" not in answer
    assert "第 4 段" not in answer
    assert "HTML Heading" not in answer
    assert "HTML Subheading" not in answer
    assert "实验组的平均值高于对照组。" in answer


async def test_graph_uses_fixed_text_for_unverified_claims() -> None:
    """部分声明未通过复核时只输出服务端固定的依据不足说明。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"实验组的平均值高于对照组。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]},{"text":"研究证实了研究者提出的全部假设。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true},{"claim_index":1,"supported":false}]}',
        ]
    )

    assert "实验组的平均值高于对照组。" in answer
    assert "研究证实了研究者提出的全部假设。" not in answer
    assert "其余问题部分未能从已引用原文中确认。" in answer


async def test_graph_abstains_when_model_cites_unknown_evidence() -> None:
    """模型构造未检索到的证据 ID 时，图固定返回依据不足说明。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"论文得出了更多结论。","evidence_quotes":[{"evidence_id":"9999","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ]
    )

    assert answer == LITERATURE_ABSTENTION


async def test_graph_abstains_when_model_quote_is_not_in_source_text() -> None:
    """服务端不接受模型改写的引文，即使它给出了有效证据 ID。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"实验组的平均值高于对照组。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组效果显著优于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ]
    )

    assert answer == LITERATURE_ABSTENTION


async def test_graph_abstains_when_support_verifier_duplicates_claim_index() -> None:
    """核验结果重复声明编号时不允许后一个结果覆盖前一个否定判断。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"实验组的平均值高于对照组。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":false},{"claim_index":0,"supported":true}]}',
        ]
    )

    assert answer == LITERATURE_ABSTENTION


async def test_graph_requires_comparisons_to_cite_every_selected_document() -> None:
    """比较回答中有支持声明未覆盖全部所选文献时必须弃答。"""
    answer = await _run_graph(
        [
            '{"claims":[{"text":"第一篇论文报告该结果。","evidence_quotes":[{"evidence_id":"9001","quote":"实验组的平均值高于对照组。"}]}]}',
            '{"claims":[{"claim_index":0,"supported":true}]}',
        ],
        task_type="comparison",
        evidence_count=2,
    )

    assert answer == LITERATURE_ABSTENTION

