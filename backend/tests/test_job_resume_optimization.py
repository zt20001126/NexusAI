"""验证简历优化工具候选的暂存与明确确认门控。"""

import json
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, ToolMessage

from agents.job_agent.nodes.resume_optimization_node import create_resume_optimization_node
from agents.job_agent.tools.stage_resume_optimization import stage_resume_optimization
from agent.schemas.tool_result import ToolResult


def test_stage_node_only_copies_candidate_without_writing() -> None:
    calls: list[dict] = []
    candidate = {"scope": "skills", "source_updated_at": "2026-01-01T00:00:00+00:00", "patch": {}}
    node = create_resume_optimization_node(
        lambda principal_id, value: calls.append(value) or "saved"
    )
    tool_result = ToolResult(success=True, data=candidate).model_dump_json()
    state = {
        "messages": [
            ToolMessage(content=tool_result, name="stage_resume_optimization", tool_call_id="call-1"),
        ]
    }

    result = node(state)

    assert result["pending_resume_optimization"] == candidate
    assert calls == []


def test_candidate_tool_returns_validated_candidate_and_rejects_out_of_scope_fields() -> None:
    timestamp = datetime.now(timezone.utc).isoformat()
    accepted = stage_resume_optimization.invoke(
        {
            "scope": "basic_info",
            "source_updated_at": timestamp,
            "patch": {"basic_info": {"intended_position": "后端工程师"}},
        }
    )
    rejected = stage_resume_optimization.invoke(
        {
            "scope": "basic_info",
            "source_updated_at": timestamp,
            "patch": {"basic_info": {"name": "被保护的字段"}},
        }
    )

    assert ToolResult.model_validate_json(accepted).success is True
    invalid_result = ToolResult.model_validate_json(rejected)
    assert invalid_result.success is False
    assert invalid_result.code == "INVALID_RESUME_CANDIDATE"


def test_only_matching_confirmation_question_can_trigger_writer() -> None:
    calls: list[dict] = []
    candidate = {"scope": "skills", "source_updated_at": "2026-01-01T00:00:00+00:00", "patch": {}}
    decision_result = json.dumps({"success": True, "data": {"questions": [{
        "id": "resume_optimization_decision",
        "options": [
            {"label": "确认采用并保存"},
            {"label": "重新生成"},
            {"label": "补充要求后重新生成"},
            {"label": "取消"},
        ],
    }]}})
    node = create_resume_optimization_node(
        lambda principal_id, value: calls.append(value) or "saved"
    )
    state = {
        "pending_resume_optimization": candidate,
        "messages": [
            ToolMessage(content=decision_result, name="ask_user_questions", tool_call_id="call-2"),
            HumanMessage(content=json.dumps({"resume_optimization_decision": "确认采用并保存"})),
        ],
    }

    result = node(state, {"configurable": {"principal_id": "test-user"}})

    assert calls == [candidate]
    assert result["pending_resume_optimization"] is None
    assert result["messages"][0].content == "简历优化保存结果：saved"


def test_unrelated_question_answer_does_not_write() -> None:
    calls: list[dict] = []
    node = create_resume_optimization_node(
        lambda principal_id, value: calls.append(value) or "saved"
    )
    state = {
        "pending_resume_optimization": {"scope": "skills"},
        "messages": [
            ToolMessage(content=json.dumps({"data": {"questions": [{"id": "other_question"}]}}), name="ask_user_questions", tool_call_id="call-3"),
            HumanMessage(content=json.dumps({"resume_optimization_decision": "确认采用并保存"})),
        ],
    }

    result = node(state)

    assert calls == []
    assert "pending_resume_optimization" not in result
