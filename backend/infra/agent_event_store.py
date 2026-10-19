"""Redis Streams 实现的智能体事件回放与跨进程取消信号。"""

from collections.abc import AsyncIterator

from redis import Redis
from redis.asyncio import Redis as AsyncRedis
from redis.exceptions import RedisError, ResponseError

from agent.errors import (
    AgentEventCursorInvalidError,
    AgentEventStreamExpiredError,
    AgentEventStoreUnavailableError,
)
from agent.streaming.events import AgentEvent, AgentEventType
from infra.settings import AppSettings


class RedisAgentEventStore:
    """按会话和运行隔离保存 SSE 事件，供 API 实例及 Worker 共同读取。"""

    def __init__(self, settings: AppSettings) -> None:
        """创建 Redis 连接；事件容量和保留时间由应用配置控制。"""
        self._redis: Redis = Redis.from_url(
            settings.celery_broker_url,
            decode_responses=True,
            socket_connect_timeout=settings.agent_event_redis_timeout_seconds,
            # XREAD 会阻塞一个完整心跳周期，读取超时需要覆盖该等待时间。
            socket_timeout=(
                settings.sse_heartbeat_seconds
                + settings.agent_event_redis_timeout_seconds
            ),
        )
        self._async_redis: AsyncRedis = AsyncRedis.from_url(
            settings.celery_broker_url,
            decode_responses=True,
            socket_connect_timeout=settings.agent_event_redis_timeout_seconds,
            socket_timeout=(
                settings.sse_heartbeat_seconds
                + settings.agent_event_redis_timeout_seconds
            ),
        )
        self._max_events = settings.agent_event_max_length
        self._ttl_seconds = settings.agent_event_ttl_seconds
        self._heartbeat_seconds = settings.sse_heartbeat_seconds

    def append(self, event: AgentEvent) -> AgentEvent:
        """原子分配本 run 游标、写入事件，并刷新有限保留期。"""
        stream_key = self._stream_key(event.conversation_id, event.run_id)
        sequence_key = f"{stream_key}:sequence"
        try:
            script = """
                local sequence = redis.call('INCR', KEYS[2])
                local event_id = tostring(sequence) .. '-0'
                redis.call('XADD', KEYS[1], 'MAXLEN', '~', ARGV[1], event_id, 'event', ARGV[2])
                redis.call('EXPIRE', KEYS[1], ARGV[3])
                -- 游标元数据比事件正文寿命更长，避免过期后同一 run 的续跑序号归零。
                redis.call('SET', KEYS[3], event_id)
                if ARGV[4] == '1' then
                    redis.call('EXPIRE', KEYS[2], ARGV[3])
                    redis.call('EXPIRE', KEYS[3], ARGV[3])
                end
                return sequence
            """
            sequence = int(self._redis.eval(
                script,
                3,
                stream_key,
                sequence_key,
                self._latest_key(event.conversation_id, event.run_id),
                self._max_events,
                event.model_dump_json(),
                self._ttl_seconds,
                1 if event.event_type in {
                    AgentEventType.RUN_COMPLETED,
                    AgentEventType.RUN_CANCELLED,
                    AgentEventType.RUN_FAILED,
                } else 0,
            ))
            event_id = f"{sequence}-0"
            return event.model_copy(update={"event_id": event_id, "sequence": sequence})
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error

    def latest_id(self, conversation_id: str, run_id: str) -> str | None:
        """查询事件流最后一个稳定游标；Redis 故障转换为安全错误。"""
        try:
            value = self._redis.get(self._latest_key(conversation_id, run_id))
            return str(value) if value else None
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error

    def last_event_type(self, conversation_id: str, run_id: str) -> AgentEventType | None:
        """读取当前保留流的末事件类型，验证运行终态是否已持久化。"""
        try:
            rows = self._redis.xrevrange(
                self._stream_key(conversation_id, run_id),
                count=1,
            )
        except ResponseError:
            return None
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error
        if not rows:
            return None
        try:
            event = AgentEvent.model_validate_json(rows[0][1]["event"])
        except (KeyError, ValueError) as error:
            raise AgentEventStoreUnavailableError() from error
        return event.event_type

    def validate_cursor(
        self,
        conversation_id: str,
        run_id: str,
        after: str | None,
        *,
        allow_missing_at_latest: bool = False,
    ) -> None:
        """在 HTTP 响應開始前识别过期或超前游标。"""
        cursor = after or "0-0"
        latest_id = self.latest_id(conversation_id, run_id)
        cursor_parts = _cursor_parts(cursor)
        latest_parts = _cursor_parts(latest_id) if latest_id is not None else (0, 0)
        if cursor_parts > latest_parts:
            raise AgentEventCursorInvalidError()
        try:
            self._check_cursor(
                self._stream_key(conversation_id, run_id),
                self._latest_key(conversation_id, run_id),
                cursor,
            )
        except AgentEventStreamExpiredError:
            if not (
                allow_missing_at_latest
                and latest_id is not None
                and cursor_parts == latest_parts
                and self._stream_is_missing(conversation_id, run_id)
            ):
                raise

    async def listen(
        self,
        *,
        conversation_id: str,
        run_id: str,
        after: str | None,
        terminal_status: str | None = None,
        allow_missing_at_latest: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        """按 Redis Stream 游标回放并等待事件；读取连接取消不触碰后台任务。"""
        cursor = after or "0-0"
        stream_key = self._stream_key(conversation_id, run_id)
        first_read = True
        while True:
            if first_read:
                self.validate_cursor(
                    conversation_id,
                    run_id,
                    after,
                    allow_missing_at_latest=allow_missing_at_latest,
                )
                first_read = False
            else:
                self._check_cursor(
                    stream_key,
                    self._latest_key(conversation_id, run_id),
                    cursor,
                )
            try:
                rows = await self._async_redis.xread(
                    {stream_key: cursor},
                    count=100,
                    block=int(self._heartbeat_seconds * 1000),
                )
            except RedisError as error:
                raise AgentEventStoreUnavailableError() from error

            if rows:
                for _, entries in rows:
                    for event_id, fields in entries:
                        if _sequence_from_id(event_id) > _sequence_from_id(cursor) + 1:
                            # Stream 裁剪可能发生在 XINFO 与 XREAD 之间；不静默跳过缺口。
                            raise AgentEventStreamExpiredError()
                        cursor = event_id
                        try:
                            event = AgentEvent.model_validate_json(fields["event"])
                        except (KeyError, ValueError) as error:
                            raise AgentEventStoreUnavailableError() from error
                        # Redis Stream ID 是唯一回放游标；覆盖运行器的内存序号，
                        # 让初次推送与重连回放的 SSE id 和 data.event_id 完全一致。
                        event = event.model_copy(
                            update={
                                "event_id": event_id,
                                "sequence": _sequence_from_id(event_id),
                            }
                        )
                        yield event
                        if event.event_type in {
                            AgentEventType.RUN_COMPLETED,
                            AgentEventType.RUN_CANCELLED,
                            AgentEventType.RUN_FAILED,
                            AgentEventType.QUESTION_REQUIRED,
                        }:
                            return
                continue

            if terminal_status in {"completed", "cancelled", "failed", "waiting"}:
                return
            yield AgentEvent(
                event_id=cursor,
                event_type=AgentEventType.HEARTBEAT,
                conversation_id=conversation_id,
                run_id=run_id,
                sequence=max(1, _sequence_from_id(cursor)),
                data={},
            )

    def request_cancel(self, run_id: str) -> None:
        """写入有时限的共享取消标志，由执行 Worker 轮询。"""
        try:
            self._redis.set(f"nexusai:agent:cancel:{run_id}", "1", ex=self._ttl_seconds)
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error

    def is_cancel_requested(self, run_id: str) -> bool:
        """查询跨进程取消标志。"""
        try:
            return bool(self._redis.exists(f"nexusai:agent:cancel:{run_id}"))
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error

    async def aclose(self) -> None:
        """释放同步写入及异步阻塞读取所用的 Redis 连接池。"""
        await self._async_redis.aclose()
        self._redis.close()

    @staticmethod
    def _stream_key(conversation_id: str, run_id: str) -> str:
        return f"nexusai:agent:events:{conversation_id}:{run_id}"

    @staticmethod
    def _latest_key(conversation_id: str, run_id: str) -> str:
        return f"nexusai:agent:latest:{conversation_id}:{run_id}"

    def _check_cursor(self, stream_key: str, latest_key: str, cursor: str) -> None:
        try:
            info = self._redis.xinfo_stream(stream_key)
        except ResponseError:
            try:
                if self._redis.get(latest_key) is not None:
                    raise AgentEventStreamExpiredError() from None
                return
            except RedisError as error:
                raise AgentEventStoreUnavailableError() from error
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error
        first_id = str(info.get("first-entry", ("0-0", {}))[0])
        if _sequence_from_id(cursor) < _sequence_from_id(first_id) - 1:
            raise AgentEventStreamExpiredError()

    def _stream_is_missing(self, conversation_id: str, run_id: str) -> bool:
        """判断事件正文 Key 已过期；基础设施错误仍转换为稳定服务错误。"""
        try:
            return not bool(self._redis.exists(self._stream_key(conversation_id, run_id)))
        except RedisError as error:
            raise AgentEventStoreUnavailableError() from error


def _sequence_from_id(event_id: str) -> int:
    """将 Redis Stream ID 的首段转换为业务事件序号。"""
    try:
        return int(event_id.split("-", maxsplit=1)[0])
    except (TypeError, ValueError):
        return 0


def _cursor_parts(event_id: str) -> tuple[int, int]:
    """解析 Redis Stream 的 millisecond-sequence 游标。"""
    first, _, second = event_id.partition("-")
    try:
        return int(first), int(second or 0)
    except ValueError:
        return 0, 0
