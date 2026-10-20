"""运行器内部事件和严格的 SSE 外发协议。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
import re
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AgentEventType(StrEnum):
    HEARTBEAT = "heartbeat"
    START = "start"
    MESSAGE = "message"
    STATUS = "status"
    END = "end"


class RunTerminalStatus(StrEnum):
    COMPLETED = "completed"
    WAITING = "waiting"
    CANCELLED = "cancelled"
    FAILED = "failed"


class ToolStatus(StrEnum):
    STARTED = "started"
    COMPLETED = "completed"


class PublicEvent(BaseModel):
    """SSE data 中唯一允许的四个顶层字段。"""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: AgentEventType
    timestamp: datetime
    data: dict[str, Any]

    @field_validator("event_id")
    @classmethod
    def validate_event_id(cls, value: str) -> str:
        """公共业务事件游标必须是 Redis Stream ID。"""
        if re.fullmatch(r"[0-9]+-[0-9]+", value) is None:
            raise ValueError("event_id must be a Redis Stream cursor")
        return value

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        """保证外发时间戳使用 UTC。"""
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class AgentEvent(BaseModel):
    """含服务端运行上下文的事件；这些上下文字段永不直接序列化到 SSE。"""

    event_id: str
    event_type: AgentEventType
    conversation_id: str
    run_id: str
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @model_validator(mode="after")
    def validate_data(self) -> Self:
        """校验事件数据形状，避免内部异常数据穿透到客户端。"""
        if self.event_type in {AgentEventType.START, AgentEventType.HEARTBEAT}:
            if self.data:
                raise ValueError(f"{self.event_type.value} data must be empty")
        elif self.event_type == AgentEventType.MESSAGE:
            operation = self.data.get("operation")
            if operation == "delta":
                if not all(isinstance(self.data.get(key), str) and self.data[key]
                           for key in ("message_id", "block_id", "text")):
                    raise ValueError("message delta requires message_id, block_id, and text")
                offset = self.data.get("offset")
                if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
                    raise ValueError("message delta requires a non-negative text offset")
            elif operation == "snapshot":
                if not isinstance(self.data.get("message_id"), str) or not self.data["message_id"]:
                    raise ValueError("message snapshot requires message_id")
                content = self.data.get("content")
                if not isinstance(content, dict) or not isinstance(content.get("blocks"), list):
                    raise ValueError("message snapshot requires content.blocks")
                for block in content["blocks"]:
                    if (
                        not isinstance(block, dict)
                        or not isinstance(block.get("id"), str)
                        or not block["id"]
                    ):
                        raise ValueError("every message block requires a stable id")
                    block_type = block.get("type")
                    if block_type not in {"text", "image", "question", "task_result"}:
                        raise ValueError("unsupported public message block")
                    self._validate_content_block(block_type, block)
            else:
                raise ValueError("message operation must be delta or snapshot")
        elif self.event_type == AgentEventType.STATUS:
            if self.data.get("status") not in {ToolStatus.STARTED.value, ToolStatus.COMPLETED.value}:
                raise ValueError("status must be started or completed")
            if not isinstance(self.data.get("tool_name"), str) or not self.data["tool_name"]:
                raise ValueError("status event requires a tool_name")
        elif self.event_type == AgentEventType.END:
            try:
                RunTerminalStatus(self.data.get("status"))
            except (TypeError, ValueError) as error:
                raise ValueError("end status must be completed, waiting, cancelled, or failed") from error
            if self.data.get("status") == RunTerminalStatus.FAILED:
                error = self.data.get("error")
                if not isinstance(error, dict) or not all(
                    isinstance(error.get(key), str) and error[key]
                    for key in ("code", "message")
                ):
                    raise ValueError("failed end requires error.code and error.message")
            elif "error" in self.data:
                raise ValueError("only failed end events may include error")
        return self

    @staticmethod
    def _validate_content_block(block_type: str, block: dict[str, Any]) -> None:
        """验证四类公开内容块的必要字段。"""
        if block_type == "text" and not isinstance(block.get("text"), str):
            raise ValueError("text block requires text")
        if block_type == "image":
            image_url = block.get("image_url")
            if not isinstance(image_url, str) or not image_url.startswith("/api/"):
                raise ValueError("image block requires an application URL")
        if block_type == "question":
            if not isinstance(block.get("questions"), list) or not block["questions"]:
                raise ValueError("question block requires a non-empty questions list")
            for key in ("question_round", "max_question_rounds"):
                if (
                    not isinstance(block.get(key), int)
                    or isinstance(block[key], bool)
                    or block[key] < 1
                ):
                    raise ValueError(f"question block requires {key}")
        if block_type == "task_result":
            for key in ("task_result_id", "agent", "generation_status"):
                if not isinstance(block.get(key), str) or not block[key]:
                    raise ValueError(f"task_result block requires {key}")
            image_url = block.get("image_url")
            if image_url is not None and (
                not isinstance(image_url, str) or not image_url.startswith("/api/")
            ):
                raise ValueError("task_result image_url must be an application URL")

    def public_event(self) -> PublicEvent:
        """移除服务端运行上下文，构造强约束的四字段事件。"""
        data = _remove_run_context(self.data)
        return PublicEvent(
            event_id=self.event_id,
            event_type=self.event_type,
            timestamp=self.timestamp,
            data=data,
        )


def _remove_run_context(value: Any) -> Any:
    """递归移除嵌套内容中的运行标识，避免其进入外发 JSON。"""
    if isinstance(value, dict):
        return {
            key: _remove_run_context(item)
            for key, item in value.items()
            if key not in {"conversation_id", "run_id"}
        }
    if isinstance(value, list):
        return [_remove_run_context(item) for item in value]
    return value


def is_run_terminal_event_type(event_type: AgentEventType | None) -> bool:
    return event_type == AgentEventType.END


def get_run_terminal_status(event: AgentEvent | None) -> RunTerminalStatus | None:
    if event is None or event.event_type != AgentEventType.END:
        return None
    try:
        return RunTerminalStatus(event.data.get("status"))
    except (TypeError, ValueError):
        return None


def is_final_run_status(status: RunTerminalStatus | str | None) -> bool:
    """waiting 结束当前监听阶段，但不会结束同一运行。"""
    try:
        return RunTerminalStatus(status) in {
            RunTerminalStatus.COMPLETED,
            RunTerminalStatus.CANCELLED,
            RunTerminalStatus.FAILED,
        }
    except (TypeError, ValueError):
        return False
