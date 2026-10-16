"""构建文献解读助手四节点图，控制检索、生成、核验和依据不足分支。"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Literal, TypedDict
from urllib.parse import quote

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from pydantic import ValidationError
from typing_extensions import Annotated

from agents.literature_reader_agent.constants import (
    LITERATURE_ABSTENTION,
    LITERATURE_EVIDENCE_QUOTE_MAX_CHARS,
    LITERATURE_GENERATION_FAILURE,
)
from agents.literature_reader_agent.prompts import (
    LITERATURE_ANSWER_PROMPT,
    LITERATURE_SUPPORT_PROMPT,
)
from agents.literature_reader_agent.retrieval import LiteratureRetrievalService
from agents.literature_reader_agent.schemas import (
    LiteratureAnswerDraft,
    LiteratureEvidence,
    LiteratureEvidenceQuote,
    LiteratureSupportDraft,
)
logger = logging.getLogger(__name__)


class LiteratureState(TypedDict, total=False):
    """LangGraph 文献状态，只持久化选中文献和证据 ID，不持久化整块正文。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    principal_id: str
    document_ids: list[str]
    task_type: str
    evidence_ids: list[str]
    sufficient_document_ids: list[str]
    sufficient: bool
    answer_draft: dict[str, Any]
    verified: bool


def build_literature_reader_agent_graph(
    checkpointer: Any,
    chat_model: BaseChatModel,
    retrieval_service: LiteratureRetrievalService,
    repository: Any,
) -> Any:
    """创建并编译文献检索、回答、引用核验和依据不足状态图。"""

    async def retrieve_evidence(state: LiteratureState) -> dict[str, Any]:
        """输入问题和选中文献 ID，输出证据 ID、任务类型和充分性路由状态。"""
        question = state.get("original_request", "").strip()
        document_ids = state.get("document_ids", [])
        principal_id = state.get("principal_id", "")
        task_type, result = await retrieval_service.retrieve(
            question,
            document_ids,
            principal_id,
        )
        sufficient_ids = set(result.sufficient_document_ids)
        requires_all = retrieval_service.task_requires_all_documents(task_type)
        sufficient = (
            len(sufficient_ids) == len(document_ids)
            if requires_all
            else bool(sufficient_ids)
        )
        return {
            "task_type": task_type,
            "evidence_ids": [item.evidence_id for item in result.evidence],
            "sufficient_document_ids": sorted(sufficient_ids),
            "sufficient": sufficient,
        }

    async def generate_answer(state: LiteratureState) -> dict[str, Any]:
        """读取本轮证据并生成中文结构化事实声明，不接收未选文献内容。"""
        evidence = _load_evidence(
            repository,
            state.get("evidence_ids", []),
            state.get("document_ids", []),
            state.get("principal_id", ""),
        )
        if not evidence:
            return {"answer_draft": LiteratureAnswerDraft(claims=[]).model_dump(mode="json")}

        payload = {
            "task_type": state.get("task_type", "question"),
            "question": state.get("original_request", ""),
            "documents": state.get("document_ids", []),
            "retrieved_evidence": [_evidence_payload(item) for item in evidence],
        }
        answer_messages = [
            SystemMessage(content=LITERATURE_ANSWER_PROMPT),
            HumanMessage(content=json.dumps(payload, ensure_ascii=False)),
        ]
        response = await chat_model.ainvoke(answer_messages)
        try:
            draft = LiteratureAnswerDraft.model_validate_json(
                _json_payload(response.content)
            )
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as error:
            logger.warning(
                "文献回答结构校验失败，将按校验反馈重试一次 error_type=%s",
                type(error).__name__,
            )
            retry_messages = [
                *answer_messages,
                response,
                HumanMessage(content=_answer_validation_feedback(error)),
            ]
            try:
                retry_response = await chat_model.ainvoke(retry_messages)
                draft = LiteratureAnswerDraft.model_validate_json(
                    _json_payload(retry_response.content)
                )
            except (
                ValidationError,
                ValueError,
                TypeError,
                json.JSONDecodeError,
            ) as retry_error:
                invalid_fields = (
                    ",".join(
                        ".".join(str(part) for part in item["loc"])
                        for item in retry_error.errors(include_input=False)
                    )
                    if isinstance(retry_error, ValidationError)
                    else "json_output"
                )
                logger.warning(
                    "文献回答结构校验重试失败 error_type=%s invalid_fields=%s",
                    type(retry_error).__name__,
                    invalid_fields,
                )
                raise RuntimeError(LITERATURE_GENERATION_FAILURE) from None

        return {"answer_draft": draft.model_dump(mode="json")}

    async def verify_and_render(state: LiteratureState) -> dict[str, Any]:
        """核对证据 ID 和逐条原文支持关系，并由服务端生成引用标注。"""
        draft = LiteratureAnswerDraft.model_validate(state.get("answer_draft", {}))
        if not draft.claims:
            return {"verified": False}

        evidence = _load_evidence(
            repository,
            state.get("evidence_ids", []),
            state.get("document_ids", []),
            state.get("principal_id", ""),
        )
        available = {item.evidence_id: item for item in evidence}
        if not available or any(
            quote.evidence_id not in available
            or not _contains_verbatim_quote(
                available[quote.evidence_id].content,
                quote.quote,
            )
            for claim in draft.claims
            for quote in claim.evidence_quotes
        ):
            return {"verified": False}

        # Step 1: 核验器只接收每条声明指定的证据原文，不会被要求补充事实。
        verification_payload = {
            "claims": [
                {
                    "claim_index": index,
                    "text": claim.text,
                    "evidence": [
                        {
                            "evidence_id": quote.evidence_id,
                            "quote": quote.quote,
                            "content": available[quote.evidence_id].content,
                        }
                        for quote in claim.evidence_quotes
                    ],
                }
                for index, claim in enumerate(draft.claims)
            ]
        }
        response = await chat_model.ainvoke(
            [
                SystemMessage(content=LITERATURE_SUPPORT_PROMPT),
                HumanMessage(content=json.dumps(verification_payload, ensure_ascii=False)),
            ]
        )
        support = LiteratureSupportDraft.model_validate_json(
            _json_payload(response.content)
        )
        support_map = {item.claim_index: item.supported for item in support.claims}
        if (
            len(support.claims) != len(draft.claims)
            or len(support_map) != len(support.claims)
            or set(support_map) != set(range(len(draft.claims)))
        ):
            return {"verified": False}

        # Step 2: 丢弃核验不通过的声明，只渲染被原文支持的事实和对应出处。
        supported_claims = [
            (claim, index)
            for index, claim in enumerate(draft.claims)
            if support_map[index]
        ]
        if not supported_claims:
            return {"verified": False}

        # Step 3: 总结和比较必须在最终保留的声明中实际引用每篇所选文献。
        if state.get("task_type") in {"comparison", "summary"}:
            covered_document_ids = {
                available[quote.evidence_id].document_id
                for claim, _ in supported_claims
                for quote in claim.evidence_quotes
            }
            if not set(state.get("document_ids", [])).issubset(covered_document_ids):
                return {"verified": False}

        answer = _render_answer(supported_claims, draft, available)
        return {
            "messages": [AIMessage(content=answer)],
            "verified": True,
        }

    def abstain(_: LiteratureState) -> dict[str, Any]:
        """证据不足或支持关系不成立时返回固定的中文说明。"""
        return {"messages": [AIMessage(content=LITERATURE_ABSTENTION)]}

    def after_retrieval(state: LiteratureState) -> Literal["generate_answer", "abstain"]:
        """充分性检查决定进入回答生成或直接依据不足分支。"""
        return "generate_answer" if state.get("sufficient") else "abstain"

    def after_verification(state: LiteratureState) -> Literal["abstain", "__end__"]:
        """只有通过证据校验和服务端引用渲染才能结束为正常回答。"""
        return END if state.get("verified") else "abstain"

    graph = StateGraph(LiteratureState)
    graph.add_node("retrieve_evidence", retrieve_evidence)
    graph.add_node("generate_answer", generate_answer)
    graph.add_node("verify_and_render", verify_and_render)
    graph.add_node("abstain", abstain)
    graph.add_edge(START, "retrieve_evidence")
    graph.add_conditional_edges(
        "retrieve_evidence",
        after_retrieval,
        {"generate_answer": "generate_answer", "abstain": "abstain"},
    )
    graph.add_edge("generate_answer", "verify_and_render")
    graph.add_conditional_edges(
        "verify_and_render",
        after_verification,
        {"abstain": "abstain", END: END},
    )
    graph.add_edge("abstain", END)
    return graph.compile(checkpointer=checkpointer)


def _load_evidence(
    repository: Any,
    evidence_ids: list[str],
    document_ids: list[str],
    principal_id: str,
) -> list[LiteratureEvidence]:
    """按证据 ID 重读正文，并由仓储再次执行主体和文献范围过滤。"""
    if not evidence_ids or not document_ids or not principal_id:
        return []
    return repository.get_evidence_by_ids(evidence_ids, document_ids, principal_id)


def _evidence_payload(evidence: LiteratureEvidence) -> dict[str, Any]:
    """构造给模型的数据边界，包含原文和定位但不允许模型自行生成位置。"""
    return {
        "evidence_id": evidence.evidence_id,
        "document_id": evidence.document_id,
        "title": evidence.title,
        "source_type": evidence.source_type,
        "chapter": evidence.chapter,
        "section": evidence.section,
        "page_start": evidence.page_start,
        "page_end": evidence.page_end,
        "paragraph_start": evidence.paragraph_start,
        "paragraph_end": evidence.paragraph_end,
        "content": evidence.content,
    }


def _json_payload(content: Any) -> str:
    """从模型文本中提取 JSON 对象；非文本或无 JSON 输出按结构失败处理。"""
    if not isinstance(content, str):
        raise TypeError("模型回答必须是 JSON 文本")
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(
            r"^```(?:json)?\s*|\s*```$",
            "",
            candidate,
            flags=re.IGNORECASE,
        )
    if not candidate.startswith("{"):
        first_object = candidate.find("{")
        last_object = candidate.rfind("}")
        if first_object < 0 or last_object < first_object:
            raise ValueError("模型回答缺少 JSON 对象")
        candidate = candidate[first_object : last_object + 1]
    return candidate


def _contains_verbatim_quote(source: str, quote: str) -> bool:
    """仅接受空白归一化后可在原文中逐字找到的模型引文。"""
    normalized_source = " ".join(source.split())
    normalized_quote = " ".join(quote.split())
    return bool(normalized_quote) and normalized_quote in normalized_source


def _answer_validation_feedback(error: Exception) -> str:
    """为模型提供不含原文输入的结构错误摘要，要求仅修正格式后完整重答。"""
    if isinstance(error, ValidationError):
        issues = [
            f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
            for item in error.errors(include_input=False)
        ]
    else:
        issues = ["输出不是符合要求的 JSON 结构"]
    details = "\n".join(issues)
    return (
        "上一次输出未通过结构校验，请根据原始问题和证据重新生成完整 JSON，"
        "不要只返回修改片段。校验错误如下：\n"
        f"{details}\n"
        f"每条 quote 必须不超过 {LITERATURE_EVIDENCE_QUOTE_MAX_CHARS} 个字符，"
        "并从对应证据逐字摘取最短且足以支持该声明的连续原文。"
    )


def _render_answer(
    supported_claims: list[tuple[Any, int]],
    draft: LiteratureAnswerDraft,
    evidence_by_id: dict[str, LiteratureEvidence],
) -> str:
    """由服务端生成来源标注；原文摘录须先通过逐字匹配校验。"""
    lines = ["### 文献支持的回答", ""]
    cited_quotes: list[tuple[LiteratureEvidence, LiteratureEvidenceQuote]] = []
    seen_quotes: set[tuple[str, str]] = set()
    for claim, _ in supported_claims:
        markers = []
        for evidence_quote in claim.evidence_quotes:
            evidence = evidence_by_id[evidence_quote.evidence_id]
            marker = _citation_marker(evidence)
            if marker not in markers:
                markers.append(marker)
            quote_key = (evidence.evidence_id, evidence_quote.quote)
            if quote_key not in seen_quotes:
                seen_quotes.add(quote_key)
                cited_quotes.append((evidence, evidence_quote))
        suffix = f" {' '.join(markers)}" if markers else ""
        lines.append(f"- {_escape_markdown(claim.text)}{suffix}")

    if len(supported_claims) < len(draft.claims):
        lines.extend(
            [
                "",
                "以下部分文献未提供足够依据：",
                "- 其余问题部分未能从已引用原文中确认。",
            ]
        )

    lines.extend(["", "### 原文摘录", ""])
    for evidence, evidence_quote in cited_quotes:
        lines.append(f"**{_citation_marker(evidence)}**")
        lines.append("")
        lines.extend(
            f"> {_escape_markdown(line)}"
            for line in evidence_quote.quote.splitlines()
            if line.strip()
        )
        lines.append("")
    return "\n".join(lines).strip()


def _citation_marker(evidence: LiteratureEvidence) -> str:
    """显示来源链接，并仅在 PDF 上附加数据库中的可用位置字段。"""
    location = []
    if evidence.source_type != "web_url":
        if evidence.chapter:
            location.append(_escape_markdown(evidence.chapter))
        else:
            location.append("章节未识别")
        if evidence.section and evidence.section != evidence.chapter:
            location.append(_escape_markdown(evidence.section))
        if evidence.page_start is not None:
            page_label = (
                f"第 {evidence.page_start}–{evidence.page_end} 页"
                if evidence.page_end and evidence.page_end != evidence.page_start
                else f"第 {evidence.page_start} 页"
            )
            location.append(page_label)
        if evidence.paragraph_start is not None:
            paragraph_label = (
                f"第 {evidence.paragraph_start}–{evidence.paragraph_end} 段"
                if evidence.paragraph_end
                and evidence.paragraph_end != evidence.paragraph_start
                else f"第 {evidence.paragraph_start} 段"
            )
            location.append(paragraph_label)
    title = f"《{evidence.title}》"
    if evidence.source_url:
        escaped_title = _escape_markdown(title)
        escaped_url = quote(evidence.source_url, safe=":/?#@!$&'*+,;=%-._~")
        title = f"[{escaped_title}]({escaped_url})"
    citation = f"{title}，{'，'.join(location)}" if location else title
    return f"〔{citation}〕"


def _escape_markdown(value: str) -> str:
    """转义来源标题中的 Markdown 控制字符，避免文献元数据注入链接结构。"""
    return re.sub(
        r"([\\`*_{}\[\]()#+\-.!|>])",
        lambda match: f"\\{match.group(0)}",
        value,
    )

