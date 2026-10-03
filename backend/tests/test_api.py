"""FastAPI 对外接口和 SSE 协议测试。"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from agent.persistence.memory import MemoryEventBus, MemoryEventSequence
from agent.runner import build_memory_runner
from agent.streaming.publisher import EventPublisher
from app.main import create_app
from app.service.agent import AgentApplicationService
from infra.settings import AppSettings
from tests.fake_models import ScriptedToolCallingProvider


def _test_lifespan(settings: AppSettings, model_provider: ScriptedToolCallingProvider):
    """为 API 测试显式注入内存 Agent，不改变应用的 PostgreSQL 默认值。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        runner = build_memory_runner(settings, model_provider=model_provider)
        event_bus = MemoryEventBus()
        event_sequence = MemoryEventSequence()
        app.state.settings = settings
        app.state.agent_service = AgentApplicationService(
            runner,
            EventPublisher(event_bus, event_sequence, settings.sse_heartbeat_seconds),
        )
        yield

    return lifespan


def _client(settings: AppSettings | None = None) -> TestClient:
    """创建带显式测试生命周期的 API 客户端。"""
    resolved_settings = settings or AppSettings(_env_file=None)
    model_provider = ScriptedToolCallingProvider()
    return TestClient(
        create_app(
            resolved_settings,
            model_provider=model_provider,
            lifespan=_test_lifespan(resolved_settings, model_provider),
        )
    )


def test_single_agent_uses_fixed_chat_route() -> None:
    """单智能体模板使用固定路由，不要求调用方理解或提交 agent_id。"""
    with _client() as client:
        response = client.post(
            "/api/agent/chat",
            json={"message": "帮我整理需求"},
        )

    assert response.status_code == 200


def test_legacy_multi_agent_discovery_route_is_removed() -> None:
    """单智能体模板不再暴露注册中心或智能体发现接口。"""
    with _client() as client:
        response = client.get("/api/agents")

    assert response.status_code == 404


def test_stream_chat_uses_stable_sse_event_contract() -> None:
    """流式接口发布命名事件和 JSON 数据，不透传 LangGraph 原始事件。"""
    with _client() as client:
        response = client.post(
            "/api/agent/chat/stream",
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


def test_legacy_agent_id_route_is_not_supported() -> None:
    """固定单智能体接口不会接受 agent_id 路径参数。"""
    with _client() as client:
        response = client.post(
            "/api/agents/missing/chat",
            json={"message": "hello"},
        )

    assert response.status_code == 404


def test_resume_endpoint_completes_paused_run() -> None:
    """API 调用方可以使用追问事件中的标识恢复并完成同一次运行。"""
    with _client() as client:
        paused_response = client.post(
            "/api/agent/chat",
            json={"message": "帮我梳理业务"},
        )
        paused_events = paused_response.json()["data"]
        question = next(
            event for event in paused_events if event["event_type"] == "question.required"
        )
        resumed_response = client.post(
            f"/api/agent/runs/{question['run_id']}/resume",
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
            "/api/agent/runs/unknown/resume",
            json={
                "conversation_id": "conversation",
                "answers": {"goal": "x" * 2_001},
            },
        )

    assert response.status_code == 422


def test_cancel_rejects_unknown_run_without_leaking_memory() -> None:
    """取消不存在运行时返回稳定错误，不把伪造标识写入取消集合。"""
    with _client() as client:
        response = client.post("/api/agent/runs/unknown/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_NOT_CANCELLABLE"


def test_production_rejects_missing_authenticated_principal() -> None:
    """生产环境不能把匿名调用方静默归并到共享开发身份。"""
    settings = AppSettings(app_env="production", _env_file=None)
    provider = ScriptedToolCallingProvider()
    with TestClient(
        create_app(
            settings,
            model_provider=provider,
            lifespan=_test_lifespan(settings, provider),
        )
    ) as client:
        response = client.post("/api/agent/chat", json={"message": "开始"})

    assert response.status_code == 401
