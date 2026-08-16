"""FastAPI 对外接口和 SSE 协议测试。"""

import json

from fastapi.testclient import TestClient

from app.main import create_app
from infra.settings import AppSettings


def _client() -> TestClient:
    """创建使用内存后端的独立测试客户端。"""
    return TestClient(create_app(AppSettings(_env_file=None)))


def test_list_agents_exposes_registered_example() -> None:
    """调用方可以发现已注册智能体，但不会看到内部图对象。"""
    with _client() as client:
        response = client.get("/api/agents")

    assert response.status_code == 200
    assert response.json()["data"][0] == {
        "agent_id": "example",
        "name": "示例需求助手",
        "description": "演示结构化追问、工具调用和恢复执行",
    }


def test_stream_chat_uses_stable_sse_event_contract() -> None:
    """流式接口发布命名事件和 JSON 数据，不透传 LangGraph 原始事件。"""
    with _client() as client:
        response = client.post(
            "/api/agents/example/chat/stream",
            json={"message": "帮我整理需求"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: question.required" in response.text
    assert "event: run.completed" not in response.text
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    events = [json.loads(line) for line in data_lines]
    question = next(event for event in events if event["event_type"] == "question.required")
    assert question["data"]["questions"][0]["id"] == "goal"


def test_unknown_agent_returns_safe_machine_readable_error() -> None:
    """不存在的智能体返回稳定错误码，不暴露 Python 异常信息。"""
    with _client() as client:
        response = client.post(
            "/api/agents/missing/chat",
            json={"message": "hello"},
        )

    assert response.status_code == 404
    assert response.json() == {
        "success": False,
        "code": "AGENT_NOT_FOUND",
        "message": "未找到指定智能体",
    }


def test_resume_endpoint_completes_paused_run() -> None:
    """API 调用方可以使用追问事件中的标识恢复并完成同一次运行。"""
    with _client() as client:
        paused_response = client.post(
            "/api/agents/example/chat",
            json={"message": "帮我梳理业务"},
        )
        paused_events = paused_response.json()["data"]
        question = next(
            event for event in paused_events if event["event_type"] == "question.required"
        )
        resumed_response = client.post(
            f"/api/agents/example/runs/{question['run_id']}/resume",
            json={
                "conversation_id": question["conversation_id"],
                "answers": {"goal": "构建售后工单智能体"},
            },
        )

    assert resumed_response.status_code == 200
    assert "event: tool.completed" in resumed_response.text
    assert resumed_response.text.count("event: run.completed") == 1
    assert "售后工单智能体" in resumed_response.text


def test_resume_rejects_unbounded_answer_text() -> None:
    """HTTP 边界拒绝无界恢复内容，防止超大数据进入图 Checkpoint。"""
    with _client() as client:
        response = client.post(
            "/api/agents/example/runs/unknown/resume",
            json={
                "conversation_id": "conversation",
                "answers": {"goal": "x" * 2_001},
            },
        )

    assert response.status_code == 422


def test_cancel_rejects_unknown_run_without_leaking_memory() -> None:
    """取消不存在运行时返回稳定错误，不把伪造标识写入取消集合。"""
    with _client() as client:
        response = client.post("/api/agents/example/runs/unknown/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_NOT_CANCELLABLE"

