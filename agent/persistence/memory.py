"""无需外部服务即可运行和测试的内存基础设施。"""

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from agent.errors import BackendNotConfiguredError, RunBusyError
from agent.schemas.run import RunRecord
from agent.streaming.events import AgentEvent


class MemoryCheckpointProvider:
    """在应用生命周期内复用同一个 MemorySaver。"""

    def __init__(self) -> None:
        self._checkpointer = MemorySaver()

    def get_checkpointer(self) -> MemorySaver:
        """返回共享 Checkpointer，以支持同一会话恢复。"""
        return self._checkpointer


class MemoryConversationStore:
    """进程内会话所有权存储。"""

    def __init__(self) -> None:
        self._conversations: dict[str, dict[str, Any]] = {}

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """保存元数据副本。"""
        self._conversations[conversation_id] = deepcopy(metadata)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """读取元数据副本。"""
        value = self._conversations.get(conversation_id)
        return deepcopy(value) if value is not None else None


class MemoryRunStore:
    """进程内运行记录存储。"""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    def save(self, record: RunRecord) -> None:
        """新增或更新运行记录。"""
        self._records[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        """按标识读取记录。"""
        return self._records.get(run_id)


class MemoryRunLock:
    """阻止同一进程内的同会话并发执行。"""

    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, conversation_id: str) -> None:
        """立即占用会话，已有运行时快速失败。"""
        lock = self._locks[conversation_id]
        if lock.locked():
            raise RunBusyError()
        await lock.acquire()

    def release(self, conversation_id: str) -> None:
        """释放会话执行权。"""
        lock = self._locks.get(conversation_id)
        if lock is not None and lock.locked():
            lock.release()


class MemoryEventSequence:
    """生成会话内单调递增序号。"""

    def __init__(self) -> None:
        self._sequences: defaultdict[str, int] = defaultdict(int)

    def next(self, conversation_id: str) -> int:
        """返回下一个序号。"""
        self._sequences[conversation_id] += 1
        return self._sequences[conversation_id]


class MemoryEventBus:
    """支持有界历史和恢复游标的进程内事件总线。"""

    def __init__(self, max_events_per_conversation: int = 1_000) -> None:
        self._max_events = max_events_per_conversation
        self._events: defaultdict[str, deque[AgentEvent]] = defaultdict(
            lambda: deque(maxlen=self._max_events)
        )
        self._subscribers: defaultdict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)

    async def publish(self, event: AgentEvent) -> None:
        """保存并广播事件，慢订阅者丢弃最早的一条待消费事件。"""
        self._events[event.conversation_id].append(event)
        for queue in tuple(self._subscribers[event.conversation_id]):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def subscribe(
        self, conversation_id: str, after: str | None = None
    ) -> AsyncIterator[AgentEvent]:
        """先从游标后重放历史，再持续等待新事件。"""
        history = list(self._events[conversation_id])
        start_index = 0
        if after is not None:
            for index, event in enumerate(history):
                if event.event_id == after:
                    start_index = index + 1
                    break
        queue: asyncio.Queue[AgentEvent] = asyncio.Queue(maxsize=self._max_events)
        self._subscribers[conversation_id].add(queue)
        try:
            for event in history[start_index:]:
                yield event
            while True:
                yield await queue.get()
        finally:
            self._subscribers[conversation_id].discard(queue)


class DisabledTaskDispatcher:
    """默认任务后端，显式拒绝提交。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """在未配置 Celery 时返回稳定业务错误。"""
        del task_name, payload
        raise BackendNotConfiguredError("celery")
