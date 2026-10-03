"""无需外部服务即可运行和测试的内存基础设施。"""

import asyncio
from collections import defaultdict
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver

from agent.errors import BackendNotConfiguredError, RunBusyError
from agent.schemas.conversation import ConversationRecord, MessageRecord
from agent.schemas.run import RunRecord


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
    ) -> None:
        """按写入顺序保存测试消息。"""
        self.messages[conversation_id].append(
            {
                "message_id": uuid4().hex,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "sequence": len(self.messages[conversation_id]) + 1,
                "role": role,
                "content": content,
                "created_at": datetime.now(timezone.utc),
            }
        )

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

    def release(self, conversation_id: str) -> None:
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


class DisabledTaskDispatcher:
    """默认任务后端，显式拒绝提交。"""

    def submit(self, task_name: str, payload: dict[str, Any]) -> str:
        """在未配置 Celery 时返回稳定业务错误。"""
        del task_name, payload
        raise BackendNotConfiguredError("celery")
