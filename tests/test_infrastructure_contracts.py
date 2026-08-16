"""内存适配器与模型 Provider 公共契约测试。"""

import pytest

from agent_core.contracts.events import AgentEvent, AgentEventType
from agent_core.errors import BackendNotConfiguredError
from agent_core.models.provider import StaticChatModelProvider
from agent_core.persistence.memory import (
    DisabledTaskDispatcher,
    MemoryConversationStore,
    MemoryEventBus,
)


def test_memory_conversation_store_returns_copy() -> None:
    """会话元数据可保存，读取方不能修改内部真实值。"""
    store = MemoryConversationStore()
    store.save("conversation", {"agent_id": "example"})

    value = store.get("conversation")
    assert value == {"agent_id": "example"}
    assert value is not None
    value["agent_id"] = "changed"
    assert store.get("conversation") == {"agent_id": "example"}


async def test_memory_event_bus_can_replay_after_cursor() -> None:
    """内存事件总线按事件游标重放后续事件，为 Redis Stream 保留相同接缝。"""
    bus = MemoryEventBus(max_events_per_conversation=10)
    first = AgentEvent(
        event_id="conversation:1",
        event_type=AgentEventType.RUN_STARTED,
        conversation_id="conversation",
        run_id="run",
        sequence=1,
    )
    second = AgentEvent(
        event_id="conversation:2",
        event_type=AgentEventType.RUN_COMPLETED,
        conversation_id="conversation",
        run_id="run",
        sequence=2,
    )
    await bus.publish(first)
    await bus.publish(second)

    subscription = bus.subscribe("conversation", after="conversation:1")
    replayed = await anext(subscription)
    await subscription.aclose()

    assert replayed.event_id == "conversation:2"


def test_disabled_dispatcher_fails_with_stable_error() -> None:
    """默认禁用的任务后端被调用时不会尝试连接 Celery。"""
    dispatcher = DisabledTaskDispatcher()

    with pytest.raises(BackendNotConfiguredError):
        dispatcher.submit("long_task", {"id": "1"})


def test_static_model_provider_is_deterministic_and_offline() -> None:
    """测试 Provider 返回确定性模型且不访问网络。"""
    model = StaticChatModelProvider(["第一条回复"]).create_chat_model()

    assert model.invoke("hello").content == "第一条回复"

