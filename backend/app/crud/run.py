"""提供智能体运行记录的 ORM 持久化及恢复查询。"""

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from agent.schemas.run import RunRecord, RunStatus
from agents.database_ids import agent_code_from_database_id, agent_database_id
from app.db.database import PostgresDatabase
from app.models.conversation import Conversation
from app.models.run import AgentRun
from app.models.user import User
from infra.snowflake import to_database_id


class PostgresRunStore:
    """运行存储适配器，保存状态并恢复 Runner 所需的运行上下文。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库会话工厂。"""
        self._database = database

    def save(self, record: RunRecord) -> None:
        """新增或更新智能体运行状态、元数据和更新时间。"""
        statement = insert(AgentRun).values(
            run_id=to_database_id(record.run_id),
            conversation_id=to_database_id(record.conversation_id),
            agent_id=agent_database_id(record.agent_id),
            status=record.status.value,
            run_metadata=record.metadata,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[AgentRun.run_id],
            set_={
                "conversation_id": statement.excluded.conversation_id,
                "agent_id": statement.excluded.agent_id,
                "status": statement.excluded.status,
                "metadata": statement.excluded["metadata"],
                "updated_at": func.now(),
            },
        )
        with self._database.session_factory.begin() as session:
            session.execute(statement)

    def get(self, run_id: str) -> RunRecord | None:
        """读取运行记录并转换为 Agent 层领域记录。"""
        statement = (
            select(AgentRun, User.account.label("principal_id"))
            .join(
                Conversation,
                Conversation.conversation_id == AgentRun.conversation_id,
            )
            .join(User, User.user_id == Conversation.owner_id)
            .where(AgentRun.run_id == to_database_id(run_id))
        )
        with self._database.session_factory() as session:
            row = session.execute(statement).one_or_none()
        if row is None:
            return None

        run, principal_id = row
        return RunRecord(
            run_id=str(run.run_id),
            conversation_id=str(run.conversation_id),
            principal_id=principal_id,
            status=RunStatus(run.status),
            metadata=dict(run.run_metadata or {}),
            agent_id=agent_code_from_database_id(run.agent_id),
        )
