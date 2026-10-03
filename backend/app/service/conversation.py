"""会话列表和消息历史查询的业务编排。"""

from agent.errors import ConversationAccessDeniedError
from agent.persistence.interfaces import ConversationStore, MessageStore
from app.schemas.conversation import (
    ConversationItem,
    ConversationListData,
    ConversationMessageItem,
    ConversationMessageListData,
)


class ConversationApplicationService:
    """负责会话归属校验、分页读取和 API DTO 转换。"""

    def __init__(
        self,
        conversation_store: ConversationStore,
        message_store: MessageStore,
    ) -> None:
        """注入会话及消息持久化协议。"""
        self._conversation_store = conversation_store
        self._message_store = message_store

    def list_conversations(
        self,
        *,
        principal_id: str,
        limit: int,
        offset: int,
    ) -> ConversationListData:
        """查询主体会话并判断是否存在下一页。

        Step 1: 按主体范围读取一条额外记录，用于判断是否还有下一页。
        Step 2: 转换为接口 Schema，避免持久化记录直接暴露给 Controller。
        """
        records = self._conversation_store.list_by_owner(
            principal_id,
            limit + 1,
            offset,
        )
        has_more = len(records) > limit
        items = [ConversationItem.model_validate(item) for item in records[:limit]]
        return ConversationListData(
            items=items,
            limit=limit,
            offset=offset,
            has_more=has_more,
            next_offset=offset + limit if has_more else None,
        )

    def list_messages(
        self,
        *,
        conversation_id: str,
        principal_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> ConversationMessageListData:
        """校验会话归属后读取较新的消息页，并按时间正序返回。

        Step 1: 验证会话存在且属于当前可信主体，避免泄露其他主体的数据。
        Step 2: 读取最新一页及一条探测记录，确定向更早消息翻页的游标。
        Step 3: 将持久化记录转换为接口 Schema，并恢复正序展示。
        """
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()

        records = self._message_store.list_by_conversation(
            conversation_id,
            limit + 1,
            before_sequence,
        )
        has_more = len(records) > limit
        page = records[:limit]
        next_before_sequence = page[-1].sequence if has_more and page else None
        items = [
            ConversationMessageItem.model_validate(record)
            for record in reversed(page)
        ]
        return ConversationMessageListData(
            items=items,
            limit=limit,
            before_sequence=before_sequence,
            next_before_sequence=next_before_sequence,
        )
