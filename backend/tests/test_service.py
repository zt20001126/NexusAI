"""应用 Service 的协议级心跳测试。"""

import asyncio
from collections.abc import AsyncIterator

from agent.persistence.memory import MemoryEventSequence
from agent.streaming.events import AgentEvent, AgentEventType
from agent.streaming.publisher import EventPublisher


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
    publisher = EventPublisher(MemoryEventSequence(), 0.01)

    events = [event async for event in publisher.with_heartbeat(_slow_event_source())]

    assert AgentEventType.HEARTBEAT in [event.event_type for event in events]
    heartbeat = next(
        event for event in events if event.event_type == AgentEventType.HEARTBEAT
    )
    assert heartbeat.run_id == "run"
    assert heartbeat.conversation_id == "conversation"
    assert any(
        event.timestamp > events[0].timestamp
        for event in events
        if event.event_type == AgentEventType.HEARTBEAT
    )
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
