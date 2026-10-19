"""覆盖 Redis Stream 回放游标与事件过期判断。"""

import pytest
from redis.exceptions import ResponseError

from agent.errors import AgentEventStreamExpiredError
from agent.streaming.events import AgentEvent, AgentEventType
from infra.agent_event_store import RedisAgentEventStore


class _FakeRedis:
    """提供事件存储测试所需的最小 Redis Stream 接口。"""

    def __init__(self, event: AgentEvent | None = None) -> None:
        self.event = event
        self.latest_event_id = "9-0" if event is not None else None

    def xinfo_stream(self, stream_key: str) -> dict[str, object]:
        del stream_key
        if self.event is None:
            raise ResponseError("no such key")
        return {"first-entry": ("9-0", {"event": self.event.model_dump_json()})}

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
        return [(next(iter(streams)), [("9-0", {"event": self.event.model_dump_json()})])]

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
    """重连时 JSON event_id/sequence 与 SSE Redis 游标保持一致。"""
    original = AgentEvent(
        event_id="conversation:1",
        event_type=AgentEventType.RUN_COMPLETED,
        conversation_id="123",
        run_id="456",
        sequence=1,
        data={"answer": "done"},
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
    assert events[0].data == {"answer": "done"}


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

