"""提供会话消息写入和倒序分页读取的 ORM 操作。"""

from sqlalchemy import func, select, update

from agent.schemas.conversation import MessageRecord
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.message import Message
from infra.snowflake import to_database_id


class PostgresMessageStore:
    """消息存储适配器，负责会话消息顺序和内容持久化。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂和消息 ID 生成器。"""
        self._database = database

    def save(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> str:
        """锁定会话、分配消息顺序并写入消息及更新时间。"""
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

            sequence = session.scalar(
                select(func.coalesce(func.max(Message.sequence), 0) + 1).where(
                    Message.conversation_id == database_conversation_id
                )
            )
            session.add(
                Message(
                    message_id=to_database_id(message_id),
                    conversation_id=database_conversation_id,
                    run_id=to_database_id(run_id),
                    sequence=sequence,
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

    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> list[MessageRecord]:
        """读取会话中最新的一页消息，并按新到旧顺序返回。"""
        statement = select(Message).where(
            Message.conversation_id == to_database_id(conversation_id)
        )
        if before_sequence is not None:
            statement = statement.where(Message.sequence < before_sequence)
        statement = statement.order_by(Message.sequence.desc()).limit(limit)
        with self._database.session_factory() as session:
            messages = session.scalars(statement).all()

        return [
            MessageRecord(
                message_id=str(message.message_id),
                conversation_id=str(message.conversation_id),
                run_id=str(message.run_id) if message.run_id is not None else None,
                sequence=message.sequence,
                role=message.role,
                content=message.content,
                created_at=message.created_at,
            )
            for message in messages
        ]
