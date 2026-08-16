"""根据配置组装通用运行时的基础设施工厂。"""

from agent_core.errors import BackendNotConfiguredError
from agent_core.persistence.memory import (
    MemoryCheckpointProvider,
    DisabledTaskDispatcher,
    MemoryConversationStore,
    MemoryEventBus,
    MemoryEventSequence,
    MemoryRunLock,
    MemoryRunStore,
)
from agent_core.registry import AgentRegistry
from agent_core.runtime.engine import AgentRuntime
from infra.settings import AppSettings


def build_memory_runtime(settings: AppSettings) -> AgentRuntime:
    """创建完全不访问网络的内存运行时。"""
    if (
        settings.checkpoint_backend != "memory"
        or settings.lock_backend != "memory"
        or settings.event_bus_backend != "memory"
        or settings.task_backend != "disabled"
    ):
        # PostgreSQL、Redis 与 Celery 当前只预留配置契约；显式启用时快速失败，
        # 避免看似启动成功却在首个请求中发生隐式连接错误。
        raise BackendNotConfiguredError("external")
    return AgentRuntime(
        registry=AgentRegistry(),
        checkpointer=MemoryCheckpointProvider().get_checkpointer(),
        run_store=MemoryRunStore(),
        run_lock=MemoryRunLock(),
        conversation_store=MemoryConversationStore(),
        event_bus=MemoryEventBus(),
        task_dispatcher=DisabledTaskDispatcher(),
        event_sequence=MemoryEventSequence(),
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        max_output_chars=settings.agent_max_output_chars,
        run_timeout_seconds=settings.agent_run_timeout_seconds,
    )


def build_runtime(settings: AppSettings) -> AgentRuntime:
    """按集中配置选择运行时后端。

    当前版本完整支持内存模式；外部模式只保留配置与协议，显式启用时
    返回稳定错误且不会尝试连接占位地址。
    """
    return build_memory_runtime(settings)
