"""持久化、互斥锁和运行协调等基础设施协议。"""

from typing import Any, Protocol

from agent.schemas.conversation import ConversationRecord, MessageRecord
from agent.schemas.run import RunRecord
from agent.schemas.task_result import ImageAttachmentRecord, TaskResultRecord, TaskResultStatus
from infra.object_storage import StoredImageObject


class ConversationStore(Protocol):
    """会话所有权元数据协议。"""

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None: ...
    def get(self, conversation_id: str) -> dict[str, Any] | None: ...
    def set_title_if_empty(self, conversation_id: str, title: str) -> None: ...
    def list_by_owner(
        self, principal_id: str, limit: int, offset: int
    ) -> list[ConversationRecord]: ...


class MessageStore(Protocol):
    """会话消息持久化协议。"""

    def save(
        self,
        conversation_id: str,
        role: str,
        content: dict[str, Any],
    ) -> str: ...
    def get_for_conversation(
        self, conversation_id: str, message_id: str
    ) -> MessageRecord | None: ...
    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_message_id: str | None,
    ) -> list[MessageRecord]: ...


class RunStore(Protocol):
    """运行记录持久化协议。"""

    def save(self, record: RunRecord) -> None: ...
    def get(self, run_id: str) -> RunRecord | None: ...


class RunLock(Protocol):
    """会话级互斥锁协议。"""

    async def acquire(self, conversation_id: str) -> None: ...
    async def release(self, conversation_id: str) -> None: ...


class EventSequence(Protocol):
    """会话内事件序号协议。"""

    def next(self, conversation_id: str) -> int: ...


class TaskDispatcher(Protocol):
    """长耗时任务提交协议。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str: ...


class TaskResultStore(Protocol):
    """统一保存不同智能体业务结果的持久化协议。"""

    def save(self, record: TaskResultRecord) -> None: ...
    def set_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool: ...
    def link_message(self, task_result_id: str, message_id: str, user_id: str) -> None: ...
    def get_owned(self, task_result_id: str, user_id: str) -> TaskResultRecord | None: ...
    def list_for_messages(
        self,
        conversation_id: str,
        message_ids: list[str],
        user_id: str,
    ) -> list[TaskResultRecord]: ...


class AttachmentStore(Protocol):
    """在对象存储中保存参考图和生成结果，并校验可信主体归属。"""

    def save(
        self,
        user_id: str,
        file_name: str,
        mime_type: str,
        image_data: bytes,
    ) -> ImageAttachmentRecord: ...
    def validate_staged(self, attachment_ids: list[str], user_id: str) -> None: ...
    def bind_to_message(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> None: ...
    def list_for_generation(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
    ) -> list[ImageAttachmentRecord]: ...
    def save_result(
        self,
        user_id: str,
        task_result_id: str,
        image_data: bytes,
        mime_type: str,
    ) -> StoredImageObject: ...
    def read_result(self, object_key: str, user_id: str) -> tuple[bytes, str]: ...
    def read_reference(self, attachment_id: str, user_id: str) -> tuple[bytes, str]: ...
