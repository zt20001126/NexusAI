"""覆盖 Redis Stream 回放游标与事件过期判断。"""

import json

import pytest
from redis.exceptions import ResponseError

from agent.errors import AgentEventStreamExpiredError
from agent.streaming.events import AgentEvent, AgentEventType, RunTerminalStatus
from infra.agent_event_store import RedisAgentEventStore


class _FakeRedis:
    """提供事件存储测试所需的最小 Redis Stream 接口。"""

    def __init__(self, event: AgentEvent | None = None) -> None:
        self.event = event
        self.latest_event_id = "9-0" if event is not None else None

    def _fields(self) -> dict[str, str]:
        if self.event is None:
            return {}
        return {
            "event_type": self.event.event_type.value,
            "timestamp": self.event.timestamp.isoformat(),
            "data": json.dumps(self.event.data),
        }

    def xinfo_stream(self, stream_key: str) -> dict[str, object]:
        del stream_key
        if self.event is None:
            raise ResponseError("no such key")
        return {"first-entry": ("9-0", self._fields())}

    async def xread(
        self,
        streams: dict[str, str],
        *,
        count: int,
        block: int,
    ) -> list[object]:
        del count, block
        if self.event is None:
            return []
        return [(next(iter(streams)), [("9-0", self._fields())])]

    def get(self, key: str) -> str | None:
        del key
        return self.latest_event_id


def _event_store(redis: _FakeRedis) -> RedisAgentEventStore:
    """绕过连接创建，将 Redis 协议替换为内存假实现。"""
    store = object.__new__(RedisAgentEventStore)
    store._redis = redis
    store._async_redis = redis
    store._heartbeat_seconds = 0.01
    return store


@pytest.mark.asyncio
async def test_replayed_event_uses_redis_stream_id_in_payload_and_cursor() -> None:
    """重连时内外事件 ID 都使用 Redis Stream 游标。"""
    original = AgentEvent(
        event_id="9-0",
        event_type=AgentEventType.END,
        conversation_id="123",
        run_id="456",
        sequence=9,
        data={"status": RunTerminalStatus.COMPLETED.value},
    )
    store = _event_store(_FakeRedis(original))

    events = [
        event async for event in store.listen(
            conversation_id="123",
            run_id="456",
            after="8-0",
        )
    ]

    assert len(events) == 1
    assert events[0].event_id == "9-0"
    assert events[0].sequence == 9
    public_event = events[0].public_event()
    assert public_event.event_id == "9-0"
    assert set(public_event.model_dump(mode="json")) == {
        "event_id",
        "event_type",
        "timestamp",
        "data",
    }


def test_public_event_strips_run_context_from_nested_content() -> None:
    """四字段外发投影递归删除会话及运行标识。"""
    event = AgentEvent(
        event_id="4-0",
        event_type=AgentEventType.MESSAGE,
        conversation_id="123",
        run_id="456",
        sequence=4,
        data={
            "operation": "snapshot",
            "message_id": "789",
            "content": {
                "blocks": [{
                    "id": "block-1",
                    "type": "question",
                    "run_id": "456",
                    "question_round": 1,
                    "max_question_rounds": 3,
                    "questions": [{"id": "q1", "title": "Choose"}],
                }]
            },
        },
    )

    public = event.public_event().model_dump(mode="json")

    assert set(public) == {"event_id", "event_type", "timestamp", "data"}
    assert public["data"]["content"]["blocks"][0] == {
        "id": "block-1",
        "type": "question",
        "question_round": 1,
        "max_question_rounds": 3,
        "questions": [{"id": "q1", "title": "Choose"}],
    }


def test_public_event_requires_redis_cursor_and_valid_content_blocks() -> None:
    """外发事件拒绝非 Redis ID 和缺字段的内容块。"""
    invalid_cursor = AgentEvent(
        event_id="conversation:1",
        event_type=AgentEventType.START,
        conversation_id="123",
        run_id="456",
        sequence=1,
    )
    with pytest.raises(ValueError):
        invalid_cursor.public_event()

    with pytest.raises(ValueError):
        AgentEvent(
            event_id="1-0",
            event_type=AgentEventType.MESSAGE,
            conversation_id="123",
            run_id="456",
            sequence=1,
            data={
                "operation": "snapshot",
                "message_id": "789",
                "content": {"blocks": [{"id": "block-1", "type": "text"}]},
            },
        )


def test_missing_stream_with_retained_cursor_is_expired() -> None:
    """事件正文过期后保留游标元数据，监听方得到可识别的恢复状态。"""
    redis = _FakeRedis()
    redis.latest_event_id = "12-0"
    store = _event_store(redis)

    with pytest.raises(AgentEventStreamExpiredError):
        store._check_cursor("stream-key", "latest-key", "10-0")


@pytest.mark.asyncio
async def test_empty_stream_without_cursor_metadata_is_not_expired() -> None:
    """任务尚未产生首个事件时，空 Stream 仍可继续等待。"""
    store = _event_store(_FakeRedis())

    store._check_cursor("stream-key", "latest-key", "0-0")

