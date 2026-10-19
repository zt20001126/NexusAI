"""提供会话所有权、标题和列表的 ORM 持久化操作。"""

from typing import Any

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from agent.constants import COMMON_AGENT_ID
from agent.schemas.conversation import ConversationRecord
from agents.database_ids import agent_code_from_database_id, agent_database_id
from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresConversationStore:
    """会话存储适配器，负责会话元数据及所有权查询。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂和雪花 ID 生成器。"""
        self._database = database

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """创建会话归属；冲突时不覆盖已有主体或智能体。"""
        owner_id = metadata.get("principal_id")
        agent_id = metadata.get("agent_id", COMMON_AGENT_ID)
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("会话必须包含有效 owner_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("会话必须包含有效 agent_id")

        with self._database.session_factory.begin() as session:
            user_id = resolve_user_id(
                session,
                owner_id,
                create=True,
                id_generator=self._database.id_generator,
            )
            session.execute(
                insert(Conversation)
                .values(
                    conversation_id=to_database_id(conversation_id),
                    owner_id=user_id,
                    agent_id=agent_database_id(agent_id),
                )
                .on_conflict_do_nothing(index_elements=[Conversation.conversation_id])
            )

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """按会话标识读取所有者和智能体元数据。"""
        statement = (
            select(User.account.label("principal_id"), Conversation.agent_id)
            .select_from(Conversation)
            .join(User, User.user_id == Conversation.owner_id)
            .where(Conversation.conversation_id == to_database_id(conversation_id))
        )
        with self._database.session_factory() as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            return None
        return {
            "principal_id": row.principal_id,
            "agent_id": agent_code_from_database_id(row.agent_id),
        }

    def set_title_if_empty(self, conversation_id: str, title: str) -> None:
        """仅在会话标题为空时保存首条用户消息摘要。"""
        statement = (
            update(Conversation)
            .where(
                Conversation.conversation_id == to_database_id(conversation_id),
                (Conversation.title.is_(None)) | (Conversation.title == ""),
            )
            .values(title=title)
        )
        with self._database.session_factory.begin() as session:
            session.execute(statement)

    def list_by_owner(
        self,
        principal_id: str,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        """按更新时间倒序分页查询当前主体的会话。"""
        with self._database.session_factory() as session:
            user_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if user_id is None:
                return []
            conversations = session.scalars(
                select(Conversation)
                .where(Conversation.owner_id == user_id)
                .order_by(Conversation.updated_at.desc(), Conversation.conversation_id.desc())
                .limit(limit)
                .offset(offset)
            ).all()

        return [
            ConversationRecord(
                conversation_id=str(conversation.conversation_id),
                title=conversation.title,
                created_at=conversation.created_at,
                updated_at=conversation.updated_at,
                agent_id=agent_code_from_database_id(conversation.agent_id),
            )
            for conversation in conversations
        ]
