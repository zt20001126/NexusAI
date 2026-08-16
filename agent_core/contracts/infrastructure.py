"""可由内存、PostgreSQL、Redis 或 Celery 实现的基础设施协议。"""

from collections.abc import AsyncIterator
from typing import Any, Protocol

from agent_core.contracts.events import AgentEvent
from agent_core.contracts.runtime import RunRecord


class CheckpointProvider(Protocol):
    """向图工厂提供具体 LangGraph Checkpointer。"""

    def get_checkpointer(self) -> Any:
        """返回应用生命周期内共享的 Checkpointer。"""
        ...


class ConversationStore(Protocol):
    """保存会话元数据的替换协议。"""

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """新增或更新会话元数据。"""
        ...

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """按标识读取会话元数据。"""
        ...


class RunStore(Protocol):
    """运行记录持久化协议。"""

    def save(self, record: RunRecord) -> None:
        """新增或更新运行记录。"""
        ...

    def get(self, run_id: str) -> RunRecord | None:
        """按运行标识查询记录。"""
        ...


class RunLock(Protocol):
    """会话级互斥锁协议。"""

    async def acquire(self, conversation_id: str) -> None:
        """占用会话执行权。"""
        ...

    def release(self, conversation_id: str) -> None:
        """释放会话执行权。"""
        ...


class EventSequence(Protocol):
    """为事件总线或直接 SSE 输出生成会话内序号。"""

    def next(self, conversation_id: str) -> int:
        """返回指定会话的下一个单调递增序号。"""
        ...

class EventBus(Protocol):
    """实时事件发布和未来断点重放协议。"""

    async def publish(self, event: AgentEvent) -> None:
        """发布一条有界事件。"""
        ...

    def subscribe(
        self,
        conversation_id: str,
        after: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """订阅会话事件；`after` 为可选恢复游标。"""
        ...


class TaskDispatcher(Protocol):
    """长耗时工作提交协议。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """提交可序列化任务并返回任务标识。"""
        ...
