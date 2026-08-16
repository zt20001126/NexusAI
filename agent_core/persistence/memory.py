"""无需外部服务即可运行和测试的内存基础设施。"""

import asyncio
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from agent_core.contracts.events import AgentEvent
from agent_core.contracts.runtime import RunRecord
from agent_core.errors import BackendNotConfiguredError, RunBusyError


class MemoryCheckpointProvider:
    """在应用生命周期内复用同一个 LangGraph MemorySaver。"""

    def __init__(self) -> None:
        """创建内存 Checkpointer，不访问外部服务。"""
        self._checkpointer = MemorySaver()

    def get_checkpointer(self) -> MemorySaver:
        """返回共享 Checkpointer，以支持同一会话恢复。"""
        return self._checkpointer


class MemoryConversationStore:
    """保存开发模式会话元数据，进程重启后允许丢失。"""

    def __init__(self) -> None:
        """初始化空会话表。"""
        self._conversations: dict[str, dict[str, Any]] = {}

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """保存元数据副本，避免调用方后续修改内部状态。"""
        self._conversations[conversation_id] = deepcopy(metadata)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """返回元数据副本；不存在时返回空值。"""
        metadata = self._conversations.get(conversation_id)
        return deepcopy(metadata) if metadata is not None else None


class MemoryRunStore:
    """保存进程生命周期内的运行记录，重启后允许丢失。"""

    def __init__(self) -> None:
        """初始化空记录表。"""
        self._records: dict[str, RunRecord] = {}

    def save(self, record: RunRecord) -> None:
        """按运行标识新增或更新记录。"""
        self._records[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        """返回记录；不存在时返回空值，由运行时转换为业务错误。"""
        return self._records.get(run_id)


class MemoryRunLock:
    """阻止同一进程内的同会话并发执行。"""

    def __init__(self) -> None:
        """按会话延迟创建异步锁。"""
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, conversation_id: str) -> None:
        """立即占用会话；已有运行时快速失败，避免请求无限等待。"""
        lock = self._locks[conversation_id]
        if lock.locked():
            raise RunBusyError()
        await lock.acquire()

    def release(self, conversation_id: str) -> None:
        """释放已占用会话；清理路径可安全重复调用。"""
        lock = self._locks.get(conversation_id)
        if lock is not None and lock.locked():
            lock.release()


class MemoryEventSequence:
    """为每个会话生成单调递增的内存事件序号。"""

    def __init__(self) -> None:
        """初始化各会话序号。"""
        self._sequences: defaultdict[str, int] = defaultdict(int)

    def next(self, conversation_id: str) -> int:
        """返回会话的下一个事件序号。"""
        self._sequences[conversation_id] += 1
        return self._sequences[conversation_id]


class MemoryEventBus:
    """支持有界历史和恢复游标的进程内事件总线。"""

    def __init__(self, max_events_per_conversation: int = 1_000) -> None:
        """初始化事件历史和订阅者队列。"""
        self._max_events = max_events_per_conversation
        self._events: defaultdict[str, deque[AgentEvent]] = defaultdict(
            lambda: deque(maxlen=self._max_events)
        )
        self._subscribers: defaultdict[str, set[asyncio.Queue[AgentEvent]]] = defaultdict(set)

    async def publish(self, event: AgentEvent) -> None:
        """保存并广播事件；慢订阅者只保留其队列可承载的最新事件。"""
        self._events[event.conversation_id].append(event)
        for queue in tuple(self._subscribers[event.conversation_id]):
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(event)

    async def subscribe(
        self,
        conversation_id: str,
        after: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """先按游标重放历史，再持续等待新事件。"""
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
    """默认任务后端；明确拒绝提交而不是隐式连接 Celery。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """拒绝任务提交；参数仅用于满足统一协议。"""
        del task_name, payload
        raise BackendNotConfiguredError("celery")
