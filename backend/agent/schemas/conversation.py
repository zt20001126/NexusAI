"""会话与消息的内部持久化记录。"""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConversationRecord:
    """会话列表所需的最小持久化数据。"""

    conversation_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class MessageRecord:
    """单条会话消息的持久化数据。"""

    message_id: str
    conversation_id: str
    run_id: str | None
    sequence: int
    role: str
    content: str
    created_at: datetime
