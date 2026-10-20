"""运行器向传输层发布的稳定事件协议。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Self

from pydantic import BaseModel, Field, model_validator


class AgentEventType(StrEnum):
    """框架对外发布的稳定事件类型。"""

    HEARTBEAT = "heartbeat"
    RUN_STARTED = "run.started"
    RUN_TERMINAL = "run.terminal"
    MESSAGE_DELTA = "message.delta"
    MESSAGE_COMPLETED = "message.completed"
    TOOL_STATUS = "tool.status"
    QUESTION_REQUIRED = "question.required"
    TASK_RESULT_UPDATED = "task_result.updated"


class ToolStatus(StrEnum):
    """统一工具状态事件中的阶段值。"""

    STARTED = "started"
    COMPLETED = "completed"


class RunTerminalStatus(StrEnum):
    """统一运行终态事件中的结果值。"""

    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ToolStatusPayload(BaseModel):
    """工具状态事件的载荷结构。"""

    status: ToolStatus = Field(description="工具阶段：started 或 completed")
    tool_name: str = Field(description="工具名称")
    tool_call_id: str | None = Field(default=None, description="模型工具调用标识")
    success: bool | None = Field(default=None, description="工具是否执行成功")
    data: dict[str, Any] | None = Field(default=None, description="安全的工具结果数据")

    @model_validator(mode="after")
    def validate_completed_result(self) -> Self:
        """完成阶段必须提供执行结果状态和结构化数据。"""
        if self.status == ToolStatus.COMPLETED and (
            self.success is None or self.data is None
        ):
            raise ValueError("工具完成事件必须包含 success 和 data")
        return self


class RunTerminalPayload(BaseModel):
    """运行终态事件的载荷结构。"""

    status: RunTerminalStatus = Field(description="运行结果状态")
    code: str | None = Field(default=None, description="稳定错误码")
    message: str | None = Field(default=None, description="用户可读错误说明")

    @model_validator(mode="after")
    def validate_failure_details(self) -> Self:
        """失败终态必须提供稳定错误码和用户可读说明。"""
        if self.status == RunTerminalStatus.FAILED and not self.code:
            raise ValueError("失败终态事件必须包含错误码")
        if self.status == RunTerminalStatus.FAILED and not self.message:
            raise ValueError("失败终态事件必须包含错误说明")
        return self


class AgentEvent(BaseModel):
    """传输层无关事件，data 禁止包含异常、密钥或原始第三方响应。"""

    event_id: str
    event_type: AgentEventType
    conversation_id: str
    run_id: str
    sequence: int = Field(ge=1)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        """校验合并后的工具和运行状态载荷。"""
        if self.event_type == AgentEventType.RUN_TERMINAL:
            RunTerminalPayload.model_validate(self.data)
        elif self.event_type == AgentEventType.TOOL_STATUS:
            ToolStatusPayload.model_validate(self.data)
        return self


def is_run_terminal_event_type(event_type: AgentEventType | None) -> bool:
    """判断事件类型是否表示运行终态。"""
    return event_type == AgentEventType.RUN_TERMINAL


def get_run_terminal_status(event: AgentEvent) -> RunTerminalStatus | None:
    """读取统一运行终态事件中的结果。"""
    if event.event_type != AgentEventType.RUN_TERMINAL:
        return None
    try:
        return RunTerminalStatus(event.data.get("status"))
    except (TypeError, ValueError):
        return None
