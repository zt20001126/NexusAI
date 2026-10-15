"""会话列表和消息历史查询的业务编排。"""

from agent.errors import ConversationAccessDeniedError
from agent.persistence.interfaces import ConversationStore, MessageStore, TaskResultStore
from app.schemas.conversation import (
    ConversationItem,
    ConversationListData,
    ConversationMessageItem,
    ConversationMessageListData,
    TaskResultSummary,
)


class ConversationApplicationService:
    """负责会话归属校验、分页读取和 API DTO 转换。"""

    def __init__(
        self,
        conversation_store: ConversationStore,
        message_store: MessageStore,
        task_result_store: TaskResultStore | None = None,
    ) -> None:
        """注入会话及消息持久化协议。"""
        self._conversation_store = conversation_store
        self._message_store = message_store
        self._task_result_store = task_result_store

    def list_conversations(
        self,
        *,
        principal_id: str,
        limit: int,
        offset: int,
    ) -> ConversationListData:
        """查询主体会话并判断是否存在下一页。

        Step 1: 按主体范围读取一条额外记录，用于判断是否还有下一页。
        Step 2: 转换为接口 Schema，避免持久化记录直接暴露给 Router。
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
        result_map: dict[str, list[TaskResultSummary]] = {}
        message_ids = [record.message_id for record in page]
        if self._task_result_store is not None and message_ids:
            for result in self._task_result_store.list_for_messages(
                conversation_id,
                message_ids,
                principal_id,
            ):
                if result.message_id is None:
                    continue
                outputs = result.result_data.get("outputs", [])
                first_output = (
                    outputs[0]
                    if isinstance(outputs, list)
                    and outputs
                    and isinstance(outputs[0], dict)
                    else {}
                )
                result_map.setdefault(result.message_id, []).append(
                    TaskResultSummary(
                        task_result_id=result.task_result_id,
                        agent_id=result.agent_id,
                        result_type=result.result_type,
                        generation_status=result.generation_status.value,
                        image_url=(
                            f"/api/task-results/{result.task_result_id}/image"
                            if first_output.get("object_key")
                            else None
                        ),
                        mime_type=first_output.get("mime_type"),
                        width=first_output.get("width"),
                        height=first_output.get("height"),
                    )
                )
        items = [
            ConversationMessageItem.model_validate(record).model_copy(
                update={"task_results": result_map.get(record.message_id, [])}
            )
            for record in reversed(page)
        ]
        return ConversationMessageListData(
            items=items,
            limit=limit,
            before_sequence=before_sequence,
            next_before_sequence=next_before_sequence,
        )
