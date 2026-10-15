"""劳动法律 RAG 回答节点，负责检索、证据校验和来源引用渲染。"""

import json
import logging
import re
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import ValidationError

from agent.state import AgentState
from agents.labor_law_agent.constants import (
    LEGAL_DEFAULT_ABSTENTION,
    LEGAL_GENERATION_FAILURE,
    LEGAL_REFERENCE_VALIDATION_FAILURE,
    LEGAL_RETRIEVAL_FAILURE,
)
from agents.labor_law_agent.prompts import LEGAL_ANSWER_PROMPT
from agents.labor_law_agent.retrieval import LegalRetrievalService
from agents.labor_law_agent.schemas import LegalAnswerDraft, LegalEvidence

logger = logging.getLogger(__name__)


def create_legal_answer_node(
    chat_model: BaseChatModel,
    retrieval_service: LegalRetrievalService,
    max_context_chars: int,
) -> Callable[..., Any]:
    """创建先检索后生成的确定性回答节点。"""

    async def legal_answer_node(state: AgentState) -> dict[str, list[AIMessage]]:
        """检索现行条文，校验模型引用 ID 后才生成带官方原文的答复。"""
        question = next(
            (
                message.content.strip()
                for message in reversed(state.get("messages", []))
                if isinstance(message, HumanMessage) and isinstance(message.content, str)
            ),
            "",
        )
        if not question:
            return {"messages": [AIMessage(content=LEGAL_DEFAULT_ABSTENTION)]}

        # Step 1: 召回条文并按证据强度判断是否允许进入生成阶段。
        try:
            retrieval_result = await retrieval_service.retrieve(question)
        except Exception as exc:
            logger.warning("劳动法律检索失败 error_type=%s", type(exc).__name__)
            return {"messages": [AIMessage(content=LEGAL_RETRIEVAL_FAILURE)]}
        if not retrieval_result.sufficient:
            return {"messages": [AIMessage(content=LEGAL_DEFAULT_ABSTENTION)]}

        evidence = _limit_context(retrieval_result.evidence, max_context_chars)
        if not evidence:
            return {"messages": [AIMessage(content=LEGAL_DEFAULT_ABSTENTION)]}

        # Step 2: 只把当前召回证据交给模型，要求结构化要点和证据 ID。
        context = [
            {
                "article_id": item.article_id,
                "law_title": item.title,
                "article_no": item.article_no,
                "chapter": item.chapter,
                "section": item.section,
                "content": item.content,
            }
            for item in evidence
        ]
        try:
            response = await chat_model.ainvoke(
                [
                    SystemMessage(content=LEGAL_ANSWER_PROMPT),
                    HumanMessage(
                        content=json.dumps(
                            {"question": question, "retrieved_evidence": context},
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
            draft = LegalAnswerDraft.model_validate_json(_json_payload(response.content))
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as exc:
            logger.warning("劳动法律回答结构校验失败 error_type=%s", type(exc).__name__)
            return {"messages": [AIMessage(content=LEGAL_GENERATION_FAILURE)]}
        except Exception as exc:
            logger.warning("劳动法律回答生成失败 error_type=%s", type(exc).__name__)
            return {"messages": [AIMessage(content=LEGAL_GENERATION_FAILURE)]}

        # Step 3: 拒绝模型引用检索范围外的 ID，再由服务端生成法条原文和官方链接。
        available = {item.article_id: item for item in evidence}
        all_referenced_ids = {
            article_id for claim in draft.claims for article_id in claim.article_ids
        }
        if not draft.claims or not all_referenced_ids or not all_referenced_ids.issubset(available):
            if not draft.claims:
                return {"messages": [AIMessage(content=LEGAL_DEFAULT_ABSTENTION)]}
            return {"messages": [AIMessage(content=LEGAL_REFERENCE_VALIDATION_FAILURE)]}
        answer = _render_answer(draft, available)
        return {"messages": [AIMessage(content=answer)]}

    return legal_answer_node


def _json_payload(content: Any) -> str:
    """提取模型纯文本 JSON；非文本输出按结构校验失败处理。"""
    if not isinstance(content, str):
        raise TypeError("模型回答必须是 JSON 文本")
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.IGNORECASE)
    if not candidate.startswith("{"):
        first_object = candidate.find("{")
        last_object = candidate.rfind("}")
        if first_object < 0 or last_object < first_object:
            raise ValueError("模型回答缺少 JSON 对象")
        candidate = candidate[first_object : last_object + 1]
    return candidate


def _limit_context(evidence: list[LegalEvidence], max_chars: int) -> list[LegalEvidence]:
    """限制上下文长度，同时保留优先级最高的完整法条。"""
    result: list[LegalEvidence] = []
    used_chars = 0
    for item in evidence:
        item_chars = len(item.content) + len(item.title) + len(item.article_no)
        if result and used_chars + item_chars > max_chars:
            break
        if item_chars > max_chars:
            continue
        result.append(item)
        used_chars += item_chars
    return result


def _render_answer(
    draft: LegalAnswerDraft,
    available: dict[str, LegalEvidence],
) -> str:
    """使用经校验的法条 ID 渲染要点、原文引用和官方来源链接。"""
    lines = ["### 可由检索条文支持的部分", ""]
    cited: dict[str, LegalEvidence] = {}
    for claim in draft.claims:
        labels = []
        for article_id in claim.article_ids:
            evidence = available[article_id]
            cited[article_id] = evidence
            labels.append(f"《{evidence.title}》{evidence.article_no}")
        lines.append(f"- {claim.text}（依据：{'、'.join(labels)}）")

    if draft.unanswered_aspects:
        lines.extend(
            [
                "",
                "以下部分的知识库依据不足，无法据此作出判断：",
                *[f"- {aspect}" for aspect in draft.unanswered_aspects],
            ]
        )

    lines.extend(["", "### 法律依据", ""])
    for evidence in cited.values():
        lines.append(f"**《{evidence.title}》{evidence.article_no}**")
        if evidence.chapter:
            lines.append(f"\n{evidence.chapter}" + (f" · {evidence.section}" if evidence.section else ""))
        quoted_text = "\n".join(f"> {line}" for line in evidence.content.splitlines())
        lines.extend(["", quoted_text, "", f"官方来源：[国家法律法规数据库]({evidence.source_url})", ""])
    return "\n".join(lines).strip()

