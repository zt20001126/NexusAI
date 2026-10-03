"""可由 PostgreSQL、Redis 或 Celery 实现的基础设施协议。"""

from collections.abc import AsyncIterator
from typing import Any, Protocol

from agent.schemas.conversation import ConversationRecord, MessageRecord
from agent.schemas.run import RunRecord
from agent.streaming.events import AgentEvent


class CheckpointProvider(Protocol):
    """LangGraph Checkpointer 提供协议。"""

    def get_checkpointer(self) -> Any:
        """返回应用生命周期内共享的 Checkpointer。"""
        ...


class ConversationStore(Protocol):
    """会话所有权元数据协议。"""

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None: ...
    def get(self, conversation_id: str) -> dict[str, Any] | None: ...
    def set_title_if_empty(self, conversation_id: str, title: str) -> None: ...
    def list_by_owner(
        self, principal_id: str, limit: int, offset: int
    ) -> list[ConversationRecord]: ...


class MessageStore(Protocol):
    """会话消息持久化协议。"""

    def save(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> None: ...
    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> list[MessageRecord]: ...


class RunStore(Protocol):
    """运行记录持久化协议。"""

    def save(self, record: RunRecord) -> None: ...
    def get(self, run_id: str) -> RunRecord | None: ...


class RunLock(Protocol):
    """会话级互斥锁协议。"""

    async def acquire(self, conversation_id: str) -> None: ...
    def release(self, conversation_id: str) -> None: ...


class EventSequence(Protocol):
    """会话内事件序号协议。"""

    def next(self, conversation_id: str) -> int: ...


class EventBus(Protocol):
    """事件发布和断点重放协议。"""

    async def publish(self, event: AgentEvent) -> None: ...
    def subscribe(
        self, conversation_id: str, after: str | None = None
    ) -> AsyncIterator[AgentEvent]: ...


class TaskDispatcher(Protocol):
    """长耗时任务提交协议。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str: ...
