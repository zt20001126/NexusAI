"""运行状态与恢复请求的领域契约。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    """一次智能体运行的生命周期状态。"""

    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class RunRecord:
    """内存运行记录；未来数据库实现应保持相同行为契约。"""

    run_id: str
    conversation_id: str
    agent_id: str
    principal_id: str
    status: RunStatus
    metadata: dict[str, Any] = field(default_factory=dict)
