"""提供统一任务结果的授权校验、状态更新和 ORM 查询。"""

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from agent.errors import ConversationAccessDeniedError
from agent.enums import AgentType
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agents.image_agent.constants import IMAGE_AGENT, IMAGE_RESULT_TYPE
from agents.listing_agent.constants import LISTING_AGENT, LISTING_RESULT_TYPE
from agents.research_agent.constants import RESEARCH_AGENT, RESEARCH_RESULT_TYPE
from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.run import AgentRun
from app.models.task_result import TaskResult
from app.models.user import User
from infra.snowflake import to_database_id


_RESULT_TYPE_BY_AGENT = {
    IMAGE_AGENT: IMAGE_RESULT_TYPE,
    LISTING_AGENT: LISTING_RESULT_TYPE,
    RESEARCH_AGENT: RESEARCH_RESULT_TYPE,
}


class PostgresTaskResultStore:
    """任务结果存储适配器，按会话所有者执行授权校验。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂。"""
        self._database = database

    def save(self, record: TaskResultRecord) -> None:
        """验证会话和运行归属后创建或更新任务结果。"""
        if record.run_id is None:
            raise ConversationAccessDeniedError()
        task_result_id = to_database_id(record.task_result_id)
        with self._database.session_factory.begin() as session:
            user_id = resolve_user_id(
                session,
                record.user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if user_id is None:
                raise ConversationAccessDeniedError()

            context_exists = session.scalar(
                select(Conversation.conversation_id)
                .join(
                    AgentRun,
                    AgentRun.conversation_id == Conversation.conversation_id,
                )
                .where(
                    Conversation.conversation_id
                    == to_database_id(record.conversation_id),
                    Conversation.owner_id == user_id,
                    Conversation.agent == record.agent.value,
                    AgentRun.run_id == to_database_id(record.run_id),
                )
                .limit(1)
            )
            if context_exists is None:
                raise ConversationAccessDeniedError()

            statement = insert(TaskResult).values(
                id=task_result_id,
                conversation_id=to_database_id(record.conversation_id),
                message_id=(
                    to_database_id(record.message_id) if record.message_id else None
                ),
                status=record.generation_status.value,
                input=record.input_data,
                result=record.result_data,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[TaskResult.id],
                set_={
                    "status": statement.excluded.status,
                    "input": statement.excluded.input,
                    "result": statement.excluded.result,
                    "message_id": func.coalesce(
                        statement.excluded.message_id,
                        TaskResult.message_id,
                    ),
                },
                where=(
                    TaskResult.conversation_id
                    == statement.excluded.conversation_id
                ),
            ).returning(TaskResult.id)
            result = session.execute(statement)
            if result.scalar_one_or_none() is None:
                raise ConversationAccessDeniedError()

    def set_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool:
        """只更新当前可信用户会话中的结果状态。"""
        with self._database.session_factory.begin() as session:
            database_user_id = resolve_user_id(
                session,
                user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if database_user_id is None:
                return False
            owned_conversations = select(Conversation.conversation_id).where(
                Conversation.owner_id == database_user_id
            )
            result = session.execute(
                update(TaskResult)
                .where(
                    TaskResult.id == to_database_id(task_result_id),
                    TaskResult.conversation_id.in_(owned_conversations),
                )
                .values(status=status.value)
                .returning(TaskResult.id)
            )
            return result.scalar_one_or_none() is not None

    def link_message(self, task_result_id: str, message_id: str, user_id: str) -> None:
        """将任务结果关联到助手消息，不改变其生成状态。"""
        with self._database.session_factory.begin() as session:
            database_user_id = resolve_user_id(
                session,
                user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if database_user_id is None:
                return
            owned_conversations = select(Conversation.conversation_id).where(
                Conversation.owner_id == database_user_id
            )
            session.execute(
                update(TaskResult)
                .where(
                    TaskResult.id == to_database_id(task_result_id),
                    TaskResult.conversation_id.in_(owned_conversations),
                )
                .values(message_id=to_database_id(message_id))
            )

    def get_owned(
        self,
        task_result_id: str,
        user_id: str,
    ) -> TaskResultRecord | None:
        """按可信用户读取拥有的任务结果及会话派生元数据。"""
        with self._database.session_factory() as session:
            database_user_id = resolve_user_id(
                session,
                user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if database_user_id is None:
                return None
            row = session.execute(
                select(
                    TaskResult,
                    User.account.label("principal_id"),
                    Conversation.agent.label("agent"),
                )
                .join(
                    Conversation,
                    Conversation.conversation_id == TaskResult.conversation_id,
                )
                .join(User, User.user_id == Conversation.owner_id)
                .where(
                    TaskResult.id == to_database_id(task_result_id),
                    Conversation.owner_id == database_user_id,
                )
            ).one_or_none()
        if row is None:
            return None
        return self._to_record(
            row[0],
            row.principal_id,
            row.agent,
        )

    def list_for_messages(
        self,
        conversation_id: str,
        message_ids: list[str],
        user_id: str,
    ) -> list[TaskResultRecord]:
        """按会话、消息和可信用户读取任务结果元数据。"""
        if not message_ids:
            return []
        database_message_ids = [to_database_id(message_id) for message_id in message_ids]
        with self._database.session_factory() as session:
            database_user_id = resolve_user_id(
                session,
                user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if database_user_id is None:
                return []
            rows = session.execute(
                select(
                    TaskResult,
                    User.account.label("principal_id"),
                    Conversation.agent.label("agent"),
                )
                .join(
                    Conversation,
                    Conversation.conversation_id == TaskResult.conversation_id,
                )
                .join(User, User.user_id == Conversation.owner_id)
                .where(
                    TaskResult.conversation_id == to_database_id(conversation_id),
                    Conversation.owner_id == database_user_id,
                    TaskResult.message_id.in_(database_message_ids),
                )
                .order_by(TaskResult.created_at)
            ).all()
        return [
            self._to_record(task_result, principal_id, agent)
            for task_result, principal_id, agent in rows
        ]

    @staticmethod
    def _to_record(
        task_result: TaskResult,
        principal_id: str,
        agent: str,
    ) -> TaskResultRecord:
        """将 ORM 实体与会话派生元数据转换成 Agent 领域记录。"""
        resolved_agent = AgentType(agent)
        return TaskResultRecord(
            task_result_id=str(task_result.id),
            agent=resolved_agent,
            user_id=principal_id,
            conversation_id=str(task_result.conversation_id),
            run_id=None,
            message_id=(
                str(task_result.message_id)
                if task_result.message_id is not None
                else None
            ),
            result_type=_RESULT_TYPE_BY_AGENT.get(resolved_agent, resolved_agent.value),
            generation_status=TaskResultStatus(task_result.status),
            input_data=dict(task_result.input or {}),
            result_data=dict(task_result.result or {}),
            created_at=task_result.created_at,
        )
