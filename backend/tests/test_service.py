"""应用 Service 的协议级心跳测试。"""

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime, timezone

from agent.persistence.memory import MemoryEventSequence, MemoryMessageStore
from agent.schemas.conversation import text_content
from agent.streaming.events import AgentEvent, AgentEventType, RunTerminalStatus
from agent.streaming.publisher import EventPublisher


async def _slow_event_source() -> AsyncIterator[AgentEvent]:
    """在两个业务事件间制造短暂无输出窗口。"""
    yield AgentEvent(
        event_id="1-0",
        event_type=AgentEventType.START,
        conversation_id="conversation",
        run_id="run",
        sequence=1,
    )
    await asyncio.sleep(0.03)
    yield AgentEvent(
        event_id="2-0",
        event_type=AgentEventType.END,
        conversation_id="conversation",
        run_id="run",
        sequence=3,
        data={"status": RunTerminalStatus.COMPLETED.value},
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
    business_events = [event for event in events if event.event_type != AgentEventType.HEARTBEAT]
    assert [event.event_id for event in business_events] == ["1-0", "2-0"]
    assert all(
        event.event_id == "1-0" and event.sequence == 1
        for event in events
        if event.event_type == AgentEventType.HEARTBEAT
    )


def test_message_history_uses_id_to_break_created_at_ties() -> None:
    """相同创建时间的消息按 ID 稳定翻页，不重复也不遗漏。"""
    store = MemoryMessageStore()
    ids = [store.save("1", "user", text_content(str(index))) for index in range(3)]
    tied_time = datetime(2026, 10, 19, tzinfo=timezone.utc)
    for item in store.messages["1"]:
        item["created_at"] = tied_time

    first_page = store.list_by_conversation("1", 2, None)
    second_page = store.list_by_conversation("1", 2, first_page[-1].message_id)

    assert [item.message_id for item in first_page + second_page] == list(reversed(ids))
