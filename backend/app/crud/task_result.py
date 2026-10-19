"""提供统一任务结果的授权校验、状态更新和 ORM 查询。"""

from sqlalchemy import and_, func, select, update
from sqlalchemy.dialects.postgresql import insert

from agent.errors import ConversationAccessDeniedError
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agents.database_ids import agent_code_from_database_id, agent_database_id
from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.run import AgentRun
from app.models.task_result import TaskResult
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresTaskResultStore:
    """任务结果存储适配器，执行主体、会话和运行归属校验。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂。"""
        self._database = database

    def save(self, record: TaskResultRecord) -> None:
        """验证会话和运行归属后创建或更新任务结果。"""
        database_agent_id = agent_database_id(record.agent_id)
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
                    Conversation.agent_id == database_agent_id,
                    AgentRun.run_id == to_database_id(record.run_id),
                    AgentRun.agent_id == database_agent_id,
                )
                .limit(1)
            )
            if context_exists is None:
                raise ConversationAccessDeniedError()

            statement = insert(TaskResult).values(
                task_result_id=task_result_id,
                agent_id=database_agent_id,
                user_id=user_id,
                conversation_id=to_database_id(record.conversation_id),
                run_id=to_database_id(record.run_id),
                message_id=(
                    to_database_id(record.message_id) if record.message_id else None
                ),
                result_type=record.result_type,
                generation_status=record.generation_status.value,
                input_data=record.input_data,
                result_data=record.result_data,
            )
            statement = statement.on_conflict_do_update(
                index_elements=[TaskResult.task_result_id],
                set_={
                    "generation_status": statement.excluded.generation_status,
                    "input_data": statement.excluded.input_data,
                    "result_data": statement.excluded.result_data,
                    "message_id": func.coalesce(
                        statement.excluded.message_id,
                        TaskResult.message_id,
                    ),
                    "updated_at": func.now(),
                },
                where=and_(
                    TaskResult.user_id == statement.excluded.user_id,
                    TaskResult.agent_id == statement.excluded.agent_id,
                    TaskResult.conversation_id == statement.excluded.conversation_id,
                    TaskResult.run_id == statement.excluded.run_id,
                ),
            ).returning(TaskResult.task_result_id)
            result = session.execute(statement)
            if result.scalar_one_or_none() is None:
                raise ConversationAccessDeniedError()

    def set_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool:
        """只更新当前可信用户拥有的结果状态。"""
        with self._database.session_factory.begin() as session:
            database_user_id = resolve_user_id(
                session,
                user_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if database_user_id is None:
                return False
            result = session.execute(
                update(TaskResult)
                .where(
                    TaskResult.task_result_id == to_database_id(task_result_id),
                    TaskResult.user_id == database_user_id,
                )
                .values(generation_status=status.value, updated_at=func.now())
                .returning(TaskResult.task_result_id)
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
            session.execute(
                update(TaskResult)
                .where(
                    TaskResult.task_result_id == to_database_id(task_result_id),
                    TaskResult.user_id == database_user_id,
                )
                .values(
                    message_id=to_database_id(message_id),
                    updated_at=func.now(),
                )
            )

    def get_owned(
        self,
        task_result_id: str,
        user_id: str,
    ) -> TaskResultRecord | None:
        """按可信用户读取拥有的任务结果及对象存储元数据。"""
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
                select(TaskResult, User.account.label("principal_id"))
                .join(
                    User,
                    User.user_id == TaskResult.user_id,
                )
                .join(
                    Conversation,
                    Conversation.conversation_id == TaskResult.conversation_id,
                )
                .where(
                    TaskResult.task_result_id == to_database_id(task_result_id),
                    TaskResult.user_id == database_user_id,
                    Conversation.owner_id == database_user_id,
                )
            ).one_or_none()
        if row is None:
            return None
        return self._to_record(row[0], row.principal_id)

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
                select(TaskResult, User.account.label("principal_id"))
                .join(
                    User,
                    User.user_id == TaskResult.user_id,
                )
                .where(
                    TaskResult.conversation_id == to_database_id(conversation_id),
                    TaskResult.user_id == database_user_id,
                    TaskResult.message_id.in_(database_message_ids),
                )
                .order_by(TaskResult.created_at)
            ).all()
        return [
            self._to_record(task_result, principal_id)
            for task_result, principal_id in rows
        ]

    @staticmethod
    def _to_record(task_result: TaskResult, principal_id: str) -> TaskResultRecord:
        """将 ORM 任务实体转换成不依赖 SQLAlchemy 的 Agent 领域记录。"""
        return TaskResultRecord(
            task_result_id=str(task_result.task_result_id),
            agent_id=agent_code_from_database_id(task_result.agent_id),
            user_id=principal_id,
            conversation_id=str(task_result.conversation_id),
            run_id=str(task_result.run_id),
            message_id=(
                str(task_result.message_id)
                if task_result.message_id is not None
                else None
            ),
            result_type=task_result.result_type,
            generation_status=TaskResultStatus(task_result.generation_status),
            input_data=dict(task_result.input_data or {}),
            result_data=dict(task_result.result_data or {}),
            created_at=task_result.created_at,
            updated_at=task_result.updated_at,
        )
