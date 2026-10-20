"""会话列表和消息历史查询的业务编排。"""

from agent.errors import AttachmentAccessDeniedError, ConversationAccessDeniedError
from agent.persistence.interfaces import AttachmentStore, ConversationStore, MessageStore, TaskResultStore
from agent.schemas.conversation import image_ids_from_content
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
        attachment_store: AttachmentStore | None = None,
    ) -> None:
        """注入会话及消息持久化协议。"""
        self._conversation_store = conversation_store
        self._message_store = message_store
        self._task_result_store = task_result_store
        self._attachment_store = attachment_store

    def read_message_attachment(
        self,
        *,
        conversation_id: str,
        message_id: str,
        attachment_id: str,
        principal_id: str,
    ) -> tuple[bytes, str]:
        """在读取私有图片前校验会话所有者和消息附件关联。"""
        conversation = self._conversation_store.get(conversation_id)
        if conversation is None or conversation.get("principal_id") != principal_id:
            raise ConversationAccessDeniedError()
        message = self._message_store.get_for_conversation(conversation_id, message_id)
        if (
            message is None
            or message.role != "user"
            or attachment_id not in image_ids_from_content(message.content)
            or self._attachment_store is None
        ):
            raise AttachmentAccessDeniedError()
        return self._attachment_store.read_reference(attachment_id, principal_id)

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
        before_message_id: str | None,
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
            before_message_id,
        )
        has_more = len(records) > limit
        page = records[:limit]
        next_before_message_id = page[-1].message_id if has_more and page else None
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
                        agent=result.agent,
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
                update={
                    "task_results": result_map.get(record.message_id, []),
                    "content": self._content_with_image_urls(record.content, conversation_id, record.message_id),
                }
            )
            for record in reversed(page)
        ]
        return ConversationMessageListData(
            items=items,
            limit=limit,
            before_message_id=before_message_id,
            next_before_message_id=next_before_message_id,
        )

    @staticmethod
    def _content_with_image_urls(
        content: dict, conversation_id: str, message_id: str
    ) -> dict:
        """仅为图片块补充受授权保护的应用路径，不修改持久化 JSON。"""
        blocks = content.get("blocks", [])
        if not isinstance(blocks, list):
            return content
        enriched = []
        for index, block in enumerate(blocks):
            if isinstance(block, dict) and block.get("type") == "image":
                attachment_id = block.get("attachment_id")
                if isinstance(attachment_id, str):
                    block = {
                        **block,
                        "image_url": (
                            f"/api/conversations/{conversation_id}/messages/"
                            f"{message_id}/attachments/{attachment_id}/image"
                        ),
                    }
            if isinstance(block, dict) and not isinstance(block.get("id"), str):
                block = {**block, "id": f"{message_id}-block-{index}"}
            enriched.append(block)
        return {**content, "blocks": enriched}
