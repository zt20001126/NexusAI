"""业务智能体向通用运行时注册时使用的公开契约。"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


GraphFactory = Callable[[Any], Any]


@dataclass(frozen=True, slots=True)
class AgentDefinition:
    """描述一个可运行的业务智能体。

    `graph_factory` 接收 Checkpointer 并返回已编译图。它只在运行时初始化阶段
    被调用，避免模块导入时建立数据库连接或创建昂贵资源。
    """

    agent_id: str
    name: str
    description: str
    graph_factory: GraphFactory
    pause_tool_names: frozenset[str] = frozenset()
    state_schema: type[Any] | None = None
    tool_names: frozenset[str] = frozenset()
    system_prompt: str | None = None

    def __post_init__(self) -> None:
        """校验公共标识，保证标识能安全用于路由和日志字段。"""
        if not self.agent_id or not self.agent_id.replace("_", "").isalnum():
            raise ValueError("agent_id 只能包含字母、数字和下划线")
