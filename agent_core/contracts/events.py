"""运行时向 HTTP、SSE 或其他传输层发布的统一事件协议。"""

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentEventType(StrEnum):
    """框架支持的稳定事件类型。"""

    HEARTBEAT = "heartbeat"
    RUN_STARTED = "run.started"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"
    TOOL_STARTED = "tool.started"
    TOOL_COMPLETED = "tool.completed"
    QUESTION_REQUIRED = "question.required"
    RUN_COMPLETED = "run.completed"
    RUN_CANCELLED = "run.cancelled"
    RUN_FAILED = "run.failed"


class AgentEvent(BaseModel):
    """传输层无关的智能体事件。

    `data` 只能保存通过节点或工具校验后的有界数据，禁止放入原始异常、
    连接字符串或第三方完整响应。
    """

    event_id: str
    event_type: AgentEventType
    conversation_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

