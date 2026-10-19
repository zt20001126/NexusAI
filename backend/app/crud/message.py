"""提供会话消息写入和倒序分页读取的 ORM 操作。"""

from typing import Any

from sqlalchemy import func, select, tuple_, update

from agent.schemas.conversation import MessageRecord
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.message import Message
from infra.snowflake import to_database_id


class PostgresMessageStore:
    """消息存储适配器，负责 JSON 内容持久化和时间游标分页。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂和消息 ID 生成器。"""
        self._database = database

    def save(
        self,
        conversation_id: str,
        role: str,
        content: dict[str, Any],
    ) -> str:
        """锁定会话后写入消息及更新时间。"""
        message_id = self._database.id_generator.next_id_string()
        database_conversation_id = to_database_id(conversation_id)
        with self._database.session_factory.begin() as session:
            conversation_exists = session.scalar(
                select(Conversation.conversation_id)
                .where(Conversation.conversation_id == database_conversation_id)
                .with_for_update()
            )
            if conversation_exists is None:
                raise ValueError("保存消息前必须先创建会话")

            session.add(
                Message(
                    message_id=to_database_id(message_id),
                    conversation_id=database_conversation_id,
                    role=role,
                    content=content,
                )
            )
            session.execute(
                update(Conversation)
                .where(Conversation.conversation_id == database_conversation_id)
                .values(updated_at=func.now())
            )
        return message_id

    def get_for_conversation(
        self, conversation_id: str, message_id: str
    ) -> MessageRecord | None:
        """按会话和消息 ID 读取一条消息，不绕过上层所有权校验。"""
        with self._database.session_factory() as session:
            message = session.scalar(
                select(Message).where(
                    Message.conversation_id == to_database_id(conversation_id),
                    Message.message_id == to_database_id(message_id),
                )
            )
            return self._to_record(message) if message is not None else None

    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_message_id: str | None,
    ) -> list[MessageRecord]:
        """读取会话中最新的一页消息，并按新到旧顺序返回。"""
        database_conversation_id = to_database_id(conversation_id)
        with self._database.session_factory() as session:
            statement = select(Message).where(
                Message.conversation_id == database_conversation_id
            )
            if before_message_id is not None:
                anchor = session.scalar(
                    select(Message).where(
                        Message.conversation_id == database_conversation_id,
                        Message.message_id == to_database_id(before_message_id),
                    )
                )
                if anchor is None:
                    return []
                statement = statement.where(
                    tuple_(Message.created_at, Message.message_id)
                    < (anchor.created_at, anchor.message_id)
                )
            statement = statement.order_by(
                Message.created_at.desc(), Message.message_id.desc()
            ).limit(limit)
            messages = session.scalars(statement).all()

        return [self._to_record(message) for message in messages]

    @staticmethod
    def _to_record(message: Message) -> MessageRecord:
        """将 ORM 行转换为不含图片字节的领域记录。"""
        return MessageRecord(
            message_id=str(message.message_id),
            conversation_id=str(message.conversation_id),
            role=message.role,
            content=dict(message.content or {"blocks": []}),
            created_at=message.created_at,
        )
