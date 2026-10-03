"""会话列表与消息历史接口的响应 Schema。"""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationItem(BaseModel):
    """会话列表中的一条会话记录。"""

    model_config = ConfigDict(from_attributes=True)

    conversation_id: str = Field(description="会话标识")
    title: str | None = Field(description="会话标题")
    created_at: datetime = Field(description="会话创建时间")
    updated_at: datetime = Field(description="会话最近更新时间")


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

    message_id: str = Field(description="消息标识")
    conversation_id: str = Field(description="所属会话标识")
    run_id: str | None = Field(description="产生消息的 Agent 运行标识")
    sequence: int = Field(description="会话内消息顺序")
    role: str = Field(description="消息角色：user 或 assistant")
    content: str = Field(description="消息正文")
    created_at: datetime = Field(description="消息创建时间")


class ConversationMessageListData(BaseModel):
    """消息历史分页数据，消息按时间正序排列。"""

    items: list[ConversationMessageItem] = Field(description="当前页消息")
    limit: int = Field(description="每页数量")
    before_sequence: int | None = Field(description="本页查询游标")
    next_before_sequence: int | None = Field(
        description="向更早消息翻页使用的游标；无更多消息时为空"
    )
