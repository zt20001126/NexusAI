"""应用 Service 的协议级心跳测试。"""

import asyncio
from collections.abc import AsyncIterator

from agent_core.contracts.events import AgentEvent, AgentEventType
from agent_core.runtime.factory import build_memory_runtime
from app.service import AgentApplicationService
from infra.settings import AppSettings


async def _slow_event_source() -> AsyncIterator[AgentEvent]:
    """在两个业务事件间制造短暂无输出窗口。"""
    yield AgentEvent(
        event_id="conversation:1",
        event_type=AgentEventType.RUN_STARTED,
        conversation_id="conversation",
        run_id="run",
        sequence=1,
    )
    await asyncio.sleep(0.03)
    yield AgentEvent(
        event_id="conversation:3",
        event_type=AgentEventType.RUN_COMPLETED,
        conversation_id="conversation",
        run_id="run",
        sequence=3,
    )


async def test_service_emits_protocol_heartbeat_while_graph_is_quiet() -> None:
    """长模型或工具调用期间使用统一 AgentEvent 心跳，而非 SSE 注释帧。"""
    runtime = build_memory_runtime(AppSettings(_env_file=None))
    service = AgentApplicationService(runtime, heartbeat_seconds=0.01)

    events = [event async for event in service.with_heartbeat(_slow_event_source())]

    assert AgentEventType.HEARTBEAT in [event.event_type for event in events]
    heartbeat = next(
        event for event in events if event.event_type == AgentEventType.HEARTBEAT
    )
    assert heartbeat.run_id == "run"
    assert heartbeat.conversation_id == "conversation"
