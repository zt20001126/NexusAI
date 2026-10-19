"""会话与消息的内部持久化记录。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from agent.constants import COMMON_AGENT
from agent.enums import AgentType


@dataclass(frozen=True)
class ConversationRecord:
    """会话列表所需的最小持久化数据。"""

    conversation_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    agent: AgentType = COMMON_AGENT


@dataclass(frozen=True)
class MessageRecord:
    """单条会话消息的持久化数据。"""

    message_id: str
    conversation_id: str
    role: str
    content: dict[str, Any]
    created_at: datetime


def text_content(text: str) -> dict[str, Any]:
    """把可见文字包装为消息内容块。"""
    return {"blocks": [{"type": "text", "text": text}]}


def image_ids_from_content(content: dict[str, Any]) -> list[str]:
    """仅提取格式正确的图片引用，避免把任意 JSON 当作附件。"""
    blocks = content.get("blocks", [])
    if not isinstance(blocks, list):
        return []
    return [
        block["attachment_id"]
        for block in blocks
        if isinstance(block, dict)
        and block.get("type") == "image"
        and isinstance(block.get("attachment_id"), str)
    ]
