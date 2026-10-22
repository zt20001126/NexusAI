"""简历优化候选暂存与确定性确认门控。"""

import json
from collections.abc import Callable
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from agent.schemas.tool_result import ToolResult
from agents.job_agent.state import JobAgentState
from agents.job_agent.tools.stage_resume_optimization import ResumeOptimizationCandidate

STAGE_TOOL = "stage_resume_optimization"
DECISION_QUESTION_ID = "resume_optimization_decision"


def create_resume_optimization_node(
    writer: Callable[[str, dict[str, Any]], str] | None,
) -> Callable[[JobAgentState, RunnableConfig], dict[str, Any]]:
    """只从待确认状态执行保存；模型没有数据库写入工具。"""

    def node(
        state: JobAgentState,
        config: RunnableConfig | None = None,
    ) -> dict[str, Any]:
        messages = state.get("messages", [])
        last = messages[-1] if messages else None
        pending = state.get("pending_resume_optimization")
        if isinstance(last, ToolMessage) and last.name == STAGE_TOOL:
            candidate = _read_validated_candidate(last)
            if candidate is not None:
                return {"pending_resume_optimization": candidate}
        if not isinstance(pending, dict) or not isinstance(last, HumanMessage):
            return {}
        try:
            answers = json.loads(last.content) if isinstance(last.content, str) else {}
        except (TypeError, ValueError):
            return {}
        question_message = next(
            (message for message in reversed(messages[:-1])
             if isinstance(message, ToolMessage) and message.name == "ask_user_questions"),
            None,
        )
        if question_message is None or not isinstance(question_message.content, str):
            return {}
        try:
            card = json.loads(question_message.content).get("data", {}).get("questions", [])
            decision_card = next(
                (item for item in card if isinstance(item, dict) and item.get("id") == DECISION_QUESTION_ID),
                None,
            )
        except (TypeError, ValueError, AttributeError):
            return {}
        if decision_card is None or len(card) != 1:
            return {}
        decision = answers.get(DECISION_QUESTION_ID) if isinstance(answers, dict) else None
        option_labels = {
            option.get("label")
            for option in decision_card.get("options", [])
            if isinstance(option, dict)
        }
        if not isinstance(decision, str) or decision not in option_labels:
            return {}
        if decision in {"确认采用并保存", "accept_and_save"} and writer is not None:
            principal_id = (config or {}).get("configurable", {}).get("principal_id")
            if not isinstance(principal_id, str) or not principal_id:
                return {
                    "pending_resume_optimization": None,
                    "messages": [
                        SystemMessage(content="简历优化保存结果：unavailable")
                    ],
                }
            result = writer(principal_id, pending)
            return {
                "pending_resume_optimization": None,
                "messages": [SystemMessage(content=f"简历优化保存结果：{result}")],
            }
        if decision in {
            "取消", "重新生成", "补充要求后重新生成",
            "cancel", "regenerate", "revise_and_regenerate",
        }:
            return {"pending_resume_optimization": None}
        return {}

    return node


def _read_validated_candidate(message: ToolMessage) -> dict[str, Any] | None:
    """仅接收候选工具实际返回且标记成功的结构化数据。"""
    if not isinstance(message.content, str):
        return None
    try:
        result = ToolResult.model_validate_json(message.content)
    except ValidationError:
        return None
    if not result.success:
        return None
    try:
        return ResumeOptimizationCandidate.model_validate(result.data).model_dump(mode="json")
    except (TypeError, ValidationError):
        return None
