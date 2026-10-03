"""一次智能体运行的生命周期模型。"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class RunStatus(StrEnum):
    """运行状态；等待回答不是完成态。"""

    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass(slots=True)
class RunRecord:
    """运行记录；持久化实现必须保持相同行为契约。"""

    run_id: str
    conversation_id: str
    principal_id: str
    status: RunStatus
    metadata: dict[str, Any] = field(default_factory=dict)
