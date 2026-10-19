"""会话列表与消息历史接口的响应 Schema。"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from agent.constants import COMMON_AGENT
from agent.enums import AgentType


class ConversationItem(BaseModel):
    """会话列表中的一条会话记录。"""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: str = Field(
        pattern=r"^[1-9][0-9]{0,18}$",
        description="会话雪花 ID",
    )
    title: str | None = Field(description="会话标题")
    created_at: datetime = Field(description="会话创建时间")
    updated_at: datetime = Field(description="会话最近更新时间")
    agent: AgentType = Field(default=COMMON_AGENT, description="所属智能体类型")


class TaskResultSummary(BaseModel):
    """附加到消息历史的任务结果元数据，不包含二进制图片内容。"""

    task_result_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$", description="任务结果雪花 ID")
    agent: AgentType = Field(description="生成结果所属智能体类型")
    result_type: str
    generation_status: str
    image_url: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    error_code: str | None = None
    error_message: str | None = None


class ConversationListData(BaseModel):
    """会话列表分页数据。"""

    items: list[ConversationItem] = Field(description="当前页会话")
    limit: int = Field(description="每页数量")
    offset: int = Field(description="当前页偏移量")
    has_more: bool = Field(description="是否还有后续会话")
    next_offset: int | None = Field(description="下一页偏移量；无后续页时为空")


class ConversationMessageItem(BaseModel):
    """对话历史中的一条用户或助手消息。"""

    model_config = ConfigDict(from_attributes=True)

    message_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$", description="消息雪花 ID")
    conversation_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$", description="所属会话雪花 ID")
    role: str = Field(description="消息角色：user 或 assistant")
    content: dict[str, Any] = Field(description="文字、图片和问题回答的 JSON 内容块")
    created_at: datetime = Field(description="消息创建时间")
    task_results: list[TaskResultSummary] = Field(default_factory=list)


class ConversationMessageListData(BaseModel):
    """消息历史分页数据，消息按时间正序排列。"""

    items: list[ConversationMessageItem] = Field(description="当前页消息")
    limit: int = Field(description="每页数量")
    before_message_id: str | None = Field(description="本页查询游标")
    next_before_message_id: str | None = Field(
        description="向更早消息翻页使用的消息 ID；无更多消息时为空"
    )
