"""无需外部服务即可运行和测试的内存基础设施。"""

import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

from langgraph.checkpoint.memory import MemorySaver

from agent.errors import (
    AttachmentAccessDeniedError,
    BackendNotConfiguredError,
    RunBusyError,
)
from agent.schemas.conversation import ConversationRecord, MessageRecord
from agent.schemas.run import RunRecord
from agent.schemas.task_result import (
    ImageAttachmentRecord,
    TaskResultRecord,
    TaskResultStatus,
)
from infra.snowflake import get_snowflake_generator


class MemoryCheckpointProvider:
    """在应用生命周期内复用同一个 MemorySaver。"""

    def __init__(self) -> None:
        self._checkpointer = MemorySaver()

    def get_checkpointer(self) -> MemorySaver:
        """返回共享 Checkpointer，以支持同一会话恢复。"""
        return self._checkpointer


class MemoryConversationStore:
    """进程内会话所有权存储。"""

    def __init__(self) -> None:
        self._conversations: dict[str, dict[str, Any]] = {}

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """保存元数据副本并维护会话时间。"""
        now = datetime.now(timezone.utc)
        existing = self._conversations.get(conversation_id, {})
        self._conversations[conversation_id] = {
            **{
                key: deepcopy(value)
                for key, value in existing.items()
                if key.startswith("_")
            },
            **deepcopy(metadata),
            "_created_at": existing.get("_created_at", now),
            "_updated_at": now,
        }

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """读取元数据副本。"""
        value = self._conversations.get(conversation_id)
        if value is None:
            return None
        return deepcopy({key: item for key, item in value.items() if not key.startswith("_")})

    def set_title_if_empty(self, conversation_id: str, title: str) -> None:
        """只在会话尚无标题时设置首条消息标题。"""
        value = self._conversations.get(conversation_id)
        if value is not None and not value.get("_title"):
            value["_title"] = title

    def list_by_owner(
        self, principal_id: str, limit: int, offset: int
    ) -> list[ConversationRecord]:
        """按最近更新时间倒序返回指定主体的会话。"""
        records = [
            ConversationRecord(
                conversation_id=conversation_id,
                title=value.get("_title"),
                created_at=value["_created_at"],
                updated_at=value["_updated_at"],
                agent_id=value.get("agent_id", "default"),
            )
            for conversation_id, value in self._conversations.items()
            if value.get("principal_id") == principal_id
        ]
        records.sort(key=lambda record: record.updated_at, reverse=True)
        return records[offset : offset + limit]


class MemoryMessageStore:
    """供测试运行器保存会话消息的进程内适配器。"""

    def __init__(self) -> None:
        self.messages: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)

    def save(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> str:
        """按写入顺序保存测试消息。"""
        message_id = get_snowflake_generator().next_id_string()
        self.messages[conversation_id].append(
            {
                "message_id": message_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "sequence": len(self.messages[conversation_id]) + 1,
                "role": role,
                "content": content,
                "created_at": datetime.now(timezone.utc),
            }
        )
        return message_id

    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> list[MessageRecord]:
        """从最新消息向前读取一页，并按新到旧顺序返回。"""
        messages = self.messages.get(conversation_id, [])
        eligible = [
            item
            for item in messages
            if before_sequence is None or item["sequence"] < before_sequence
        ]
        return [
            MessageRecord(**item)
            for item in reversed(eligible[-limit:])
        ]


class MemoryRunStore:
    """进程内运行记录存储。"""

    def __init__(self) -> None:
        self._records: dict[str, RunRecord] = {}

    def save(self, record: RunRecord) -> None:
        """新增或更新运行记录。"""
        self._records[record.run_id] = record

    def get(self, run_id: str) -> RunRecord | None:
        """按标识读取记录。"""
        return self._records.get(run_id)


class MemoryRunLock:
    """阻止同一进程内的同会话并发执行。"""

    def __init__(self) -> None:
        self._locks: defaultdict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    async def acquire(self, conversation_id: str) -> None:
        """立即占用会话，已有运行时快速失败。"""
        lock = self._locks[conversation_id]
        if lock.locked():
            raise RunBusyError()
        await lock.acquire()

    async def release(self, conversation_id: str) -> None:
        """释放会话执行权。"""
        lock = self._locks.get(conversation_id)
        if lock is not None and lock.locked():
            lock.release()


class MemoryEventSequence:
    """生成会话内单调递增序号。"""

    def __init__(self) -> None:
        self._sequences: defaultdict[str, int] = defaultdict(int)

    def next(self, conversation_id: str) -> int:
        """返回下一个序号。"""
        self._sequences[conversation_id] += 1
        return self._sequences[conversation_id]


class MemoryTaskResultStore:
    """保存结果记录的内存适配器，供图节点与 API 测试显式注入。"""

    def __init__(self) -> None:
        self.records: dict[str, TaskResultRecord] = {}

    def save(self, record: TaskResultRecord) -> None:
        """新增或替换结果状态，同时保留初次创建时间。"""
        existing = self.records.get(record.task_result_id)
        self.records[record.task_result_id] = TaskResultRecord(
            **{
                **record.__dict__,
                "created_at": record.created_at or (
                    existing.created_at if existing is not None else datetime.now(timezone.utc)
                ),
                "updated_at": datetime.now(timezone.utc),
            }
        )

    def set_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool:
        """按结果所有者更新状态，不单独保存失败详情。"""
        from dataclasses import replace

        record = self.records.get(task_result_id)
        if record is None or record.user_id != user_id:
            return False
        self.records[task_result_id] = replace(
            record,
            generation_status=status,
            updated_at=datetime.now(timezone.utc),
        )
        return True

    def link_message(self, task_result_id: str, message_id: str, user_id: str) -> None:
        """将结果关联到助手最终回复。"""
        from dataclasses import replace

        record = self.records.get(task_result_id)
        if record is not None and record.user_id == user_id:
            self.records[task_result_id] = replace(
                record,
                message_id=message_id,
                updated_at=datetime.now(timezone.utc),
            )

    def get_owned(self, task_result_id: str, user_id: str) -> TaskResultRecord | None:
        """按可信主体读取结果记录。"""
        record = self.records.get(task_result_id)
        return record if record is not None and record.user_id == user_id else None

    def list_for_messages(
        self,
        conversation_id: str,
        message_ids: list[str],
        user_id: str,
    ) -> list[TaskResultRecord]:
        """按会话、消息和所有者读取历史结果。"""
        message_id_set = set(message_ids)
        return [
            record
            for record in self.records.values()
            if record.user_id == user_id
            and record.conversation_id == conversation_id
            and record.message_id in message_id_set
        ]


class MemoryAttachmentStore:
    """供测试显式使用的参考图片附件适配器。"""

    def __init__(self) -> None:
        self.records: dict[str, ImageAttachmentRecord] = {}
        self.result_objects: dict[str, tuple[str, bytes]] = {}

    def save(
        self,
        user_id: str,
        file_name: str,
        mime_type: str,
        image_data: bytes,
    ) -> ImageAttachmentRecord:
        """创建用户私有的暂存参考图。"""
        attachment_id = get_snowflake_generator().next_id_string()
        record = ImageAttachmentRecord(
            attachment_id=attachment_id,
            user_id=user_id,
            conversation_id=None,
            message_id=None,
            file_name=file_name,
            mime_type=mime_type,
            file_size=len(image_data),
            image_data=image_data,
            status="staged",
            object_key=f"memory/references/{user_id}/{attachment_id}",
            created_at=datetime.now(timezone.utc),
        )
        self.records[record.attachment_id] = record
        return record

    def validate_staged(self, attachment_ids: list[str], user_id: str) -> None:
        """在运行记录落库前确认附件属于当前用户且尚未绑定或过期。"""
        if len(set(attachment_ids)) != len(attachment_ids):
            raise AttachmentAccessDeniedError()
        valid_until = datetime.now(timezone.utc) - timedelta(hours=24)
        for attachment_id in attachment_ids:
            record = self.records.get(attachment_id)
            if (
                record is None
                or record.user_id != user_id
                or record.status != "staged"
                or record.created_at is None
                or record.created_at < valid_until
            ):
                raise AttachmentAccessDeniedError()

    def bind_to_message(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> None:
        """绑定本主体的暂存图片到聊天消息。"""
        from dataclasses import replace

        pending_records: list[ImageAttachmentRecord] = []
        if len(set(attachment_ids)) != len(attachment_ids):
            raise AttachmentAccessDeniedError()
        for attachment_id in attachment_ids:
            record = self.records.get(attachment_id)
            if (
                record is None
                or record.user_id != user_id
                or record.status != "staged"
            ):
                raise AttachmentAccessDeniedError()
            pending_records.append(record)
        for record in pending_records:
            attachment_id = record.attachment_id
            self.records[attachment_id] = replace(
                record,
                conversation_id=conversation_id,
                message_id=message_id,
                status="attached",
            )

    def list_for_generation(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
    ) -> list[ImageAttachmentRecord]:
        """只返回当前用户在同一会话中已绑定的参考图。"""
        records: list[ImageAttachmentRecord] = []
        for attachment_id in attachment_ids:
            record = self.records.get(attachment_id)
            if (
                record is None
                or record.user_id != user_id
                or record.conversation_id != conversation_id
                or record.status != "attached"
            ):
                raise AttachmentAccessDeniedError()
            records.append(record)
        return records

    def save_result(
        self,
        user_id: str,
        task_result_id: str,
        image_data: bytes,
        mime_type: str,
    ) -> Any:
        """在测试适配器中保存结果字节并返回与 OSS 一致的元数据结构。"""
        from infra.object_storage import StoredImageObject

        object_key = f"memory/generated/{user_id}/{task_result_id}"
        self.result_objects[object_key] = (mime_type, image_data)
        return StoredImageObject(object_key, mime_type, len(image_data))

    def read_result(self, object_key: str, user_id: str) -> tuple[bytes, str]:
        """按测试用户隔离读取内存中的生成结果。"""
        if not object_key.startswith(f"memory/generated/{user_id}/"):
            raise AttachmentAccessDeniedError()
        result = self.result_objects.get(object_key)
        if result is None:
            raise AttachmentAccessDeniedError()
        mime_type, image_data = result
        return image_data, mime_type


class DisabledTaskDispatcher:
    """默认任务后端，显式拒绝提交。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """在未配置 Celery 时返回稳定业务错误。"""
        del task_name, payload
        raise BackendNotConfiguredError("celery")
