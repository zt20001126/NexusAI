"""PostgreSQL 持久化适配器，保存会话、消息和 Agent 运行记录。"""

import asyncio
from threading import Lock
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from agent.schemas.run import RunRecord, RunStatus
from agent.errors import ConversationAccessDeniedError, RunBusyError
from agent.schemas.conversation import ConversationRecord, MessageRecord
from agent.schemas.task_result import (
    TaskResultRecord,
    TaskResultStatus,
)
from agents.database_ids import agent_code_from_database_id, agent_database_id
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator, to_database_id


class PostgresRuntimeStore:
    """集中管理会话、消息和运行记录的 PostgreSQL 连接池。"""

    def __init__(
        self,
        database_url: str,
        id_generator: SnowflakeIdGenerator | None = None,
    ) -> None:
        """创建连接池；连接串由配置层提供，不在此处读取环境变量。"""
        normalized_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._pool = ConnectionPool(
            conninfo=normalized_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )
        self.id_generator = id_generator or get_snowflake_generator()

    def __enter__(self) -> "PostgresRuntimeStore":
        """打开连接池并确保应用元数据表存在。"""
        self._pool.open(wait=True)
        self._create_tables()
        return self

    def __exit__(self, *_: object) -> None:
        """应用关闭时释放 PostgreSQL 连接。"""
        self._pool.close()

    def _create_tables(self) -> None:
        """初始化应用业务表；LangGraph 检查点由其官方适配器单独管理。"""
        statements = (
            """
            CREATE TABLE IF NOT EXISTS user_identities (
                user_id BIGINT PRIMARY KEY,
                external_principal TEXT NOT NULL UNIQUE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id BIGINT PRIMARY KEY,
                owner_id BIGINT NOT NULL REFERENCES user_identities(user_id),
                agent_id BIGINT NOT NULL,
                title TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id BIGINT PRIMARY KEY,
                conversation_id BIGINT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                agent_id BIGINT NOT NULL,
                status TEXT NOT NULL CHECK (
                    status IN ('running', 'waiting', 'completed', 'cancelled', 'failed')
                ),
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation_id
            ON agent_runs (conversation_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS messages (
                message_id BIGINT PRIMARY KEY,
                conversation_id BIGINT NOT NULL,
                run_id BIGINT REFERENCES agent_runs(run_id) ON DELETE SET NULL,
                sequence BIGINT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (conversation_id, sequence),
                FOREIGN KEY (conversation_id)
                    REFERENCES conversations(conversation_id) ON DELETE CASCADE
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_conversations_owner_updated
            ON conversations (owner_id, updated_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_messages_conversation_sequence
            ON messages (conversation_id, sequence)
            """,
            """
            CREATE TABLE IF NOT EXISTS task_results (
                task_result_id BIGINT PRIMARY KEY,
                agent_id BIGINT NOT NULL,
                user_id BIGINT NOT NULL REFERENCES user_identities(user_id),
                conversation_id BIGINT NOT NULL
                    REFERENCES conversations(conversation_id) ON DELETE CASCADE,
                run_id BIGINT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
                message_id BIGINT REFERENCES messages(message_id) ON DELETE SET NULL,
                result_type TEXT NOT NULL,
                generation_status TEXT NOT NULL CHECK (
                    generation_status IN (
                        'pending', 'awaiting_input', 'running',
                        'succeeded', 'failed', 'cancelled'
                    )
                ),
                input_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                result_data JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_task_results_user_created
            ON task_results (user_id, created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_task_results_conversation_created
            ON task_results (conversation_id, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_task_results_run
            ON task_results (run_id)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_task_results_agent_created
            ON task_results (agent_id, created_at)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_task_results_message
            ON task_results (message_id)
            """,
        )
        with self._pool.connection() as connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute("COMMENT ON TABLE conversations IS '智能体对话会话'")
            connection.execute("COMMENT ON TABLE messages IS '会话中的用户消息和助手回复'")
            connection.execute("COMMENT ON TABLE agent_runs IS '智能体运行状态与恢复信息'")
            connection.execute("COMMENT ON TABLE user_identities IS '可信外部主体与内部雪花用户 ID 的映射'")
            connection.execute("COMMENT ON TABLE task_results IS '所有智能体共享的任务结果及 OSS 对象元数据'")
            connection.execute("COMMENT ON COLUMN task_results.input_data IS '任务输入、参数和参考图 OSS 对象元数据'")
            connection.execute("COMMENT ON COLUMN task_results.result_data IS '生成结果 OSS 对象元数据及智能体扩展数据'")

    def _resolve_user_id(
        self,
        connection: Any,
        principal_id: str,
        *,
        create: bool,
    ) -> int | None:
        """将认证上下文中的外部主体映射为数据库使用的雪花用户 ID。"""
        row = connection.execute(
            "SELECT user_id FROM user_identities WHERE external_principal = %s",
            (principal_id,),
        ).fetchone()
        if row is not None:
            return row["user_id"]
        if not create:
            return None

        generated_id = self.id_generator.next_id()
        connection.execute(
            """
            INSERT INTO user_identities (user_id, external_principal)
            VALUES (%s, %s)
            ON CONFLICT (external_principal) DO NOTHING
            """,
            (generated_id, principal_id),
        )
        row = connection.execute(
            "SELECT user_id FROM user_identities WHERE external_principal = %s",
            (principal_id,),
        ).fetchone()
        if row is None:
            raise RuntimeError("无法分配数据库用户 ID")
        return row["user_id"]

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """创建会话归属；冲突时不覆盖已有主体或智能体。"""
        owner_id = metadata.get("principal_id")
        agent_id = metadata.get("agent_id", "default")
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("会话必须包含有效 owner_id")
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("会话必须包含有效 agent_id")
        with self._pool.connection() as connection:
            user_id = self._resolve_user_id(connection, owner_id, create=True)
            connection.execute(
                """
                INSERT INTO conversations (conversation_id, owner_id, agent_id)
                VALUES (%s, %s, %s)
                ON CONFLICT (conversation_id) DO NOTHING
                """,
                (
                    to_database_id(conversation_id),
                    user_id,
                    agent_database_id(agent_id),
                ),
            )

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """按会话标识读取元数据副本。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT identities.external_principal, conversations.agent_id
                FROM conversations
                JOIN user_identities AS identities ON identities.user_id = conversations.owner_id
                WHERE conversations.conversation_id = %s
                """,
                (to_database_id(conversation_id),),
            ).fetchone()
        return (
            {
                "principal_id": row["external_principal"],
                "agent_id": agent_code_from_database_id(row["agent_id"]),
            }
            if row is not None
            else None
        )

    def set_conversation_title_if_empty(self, conversation_id: str, title: str) -> None:
        """只在会话标题为空时保存首条用户消息摘要。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE conversations
                SET title = %s
                WHERE conversation_id = %s AND (title IS NULL OR title = '')
                """,
                (title, to_database_id(conversation_id)),
            )

    def list_conversations(
        self,
        principal_id: str,
        limit: int,
        offset: int,
    ) -> list[ConversationRecord]:
        """按更新时间倒序分页查询当前主体的会话。"""
        with self._pool.connection() as connection:
            user_id = self._resolve_user_id(connection, principal_id, create=False)
            if user_id is None:
                return []
            rows = connection.execute(
                """
                SELECT conversation_id, title, created_at, updated_at, agent_id
                FROM conversations
                WHERE owner_id = %s
                ORDER BY updated_at DESC, conversation_id DESC
                LIMIT %s OFFSET %s
                """,
                (user_id, limit, offset),
            ).fetchall()
        return [
            ConversationRecord(
                conversation_id=str(row["conversation_id"]),
                title=row["title"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
                agent_id=agent_code_from_database_id(row["agent_id"]),
            )
            for row in rows
        ]

    def save_message(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> str:
        """按会话锁分配消息序号并返回持久化消息标识。"""
        message_id = self.id_generator.next_id_string()
        database_conversation_id = to_database_id(conversation_id)
        database_run_id = to_database_id(run_id)
        with self._pool.connection() as connection:
            with connection.transaction():
                conversation = connection.execute(
                    "SELECT 1 FROM conversations WHERE conversation_id = %s FOR UPDATE",
                    (database_conversation_id,),
                ).fetchone()
                if conversation is None:
                    raise ValueError("保存消息前必须先创建会话")
                sequence = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                    FROM messages WHERE conversation_id = %s
                    """,
                    (database_conversation_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id, conversation_id, run_id, sequence, role, content
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        to_database_id(message_id),
                        database_conversation_id,
                        database_run_id,
                        sequence,
                        role,
                        content,
                    ),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = NOW() WHERE conversation_id = %s",
                    (database_conversation_id,),
                )
        return message_id

    def list_messages(
        self,
        conversation_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> list[MessageRecord]:
        """从最新消息向前分页查询，并按新到旧顺序返回。"""
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT message_id, conversation_id, run_id, sequence,
                       role, content, created_at
                FROM messages
                WHERE conversation_id = %s
                  AND (%s::BIGINT IS NULL OR sequence < %s)
                ORDER BY sequence DESC
                LIMIT %s
                """,
                (
                    to_database_id(conversation_id),
                    before_sequence,
                    before_sequence,
                    limit,
                ),
            ).fetchall()
        return [
            MessageRecord(
                message_id=str(row["message_id"]),
                conversation_id=str(row["conversation_id"]),
                run_id=str(row["run_id"]) if row["run_id"] is not None else None,
                sequence=row["sequence"],
                role=row["role"],
                content=row["content"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def save_run(self, record: RunRecord) -> None:
        """持久化新增或更新的智能体运行记录。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, conversation_id, agent_id, status, metadata
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    conversation_id = EXCLUDED.conversation_id,
                    agent_id = EXCLUDED.agent_id,
                    status = EXCLUDED.status,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                (
                    to_database_id(record.run_id),
                    to_database_id(record.conversation_id),
                    agent_database_id(record.agent_id),
                    record.status.value,
                    Jsonb(record.metadata),
                ),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        """读取运行记录并恢复为领域数据对象。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT runs.run_id, runs.conversation_id, conversations.owner_id,
                       identities.external_principal, runs.agent_id, runs.status,
                       runs.metadata
                FROM agent_runs AS runs
                JOIN conversations USING (conversation_id)
                JOIN user_identities AS identities ON identities.user_id = conversations.owner_id
                WHERE runs.run_id = %s
                """,
                (to_database_id(run_id),),
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=str(row["run_id"]),
            conversation_id=str(row["conversation_id"]),
            principal_id=row["external_principal"],
            status=RunStatus(row["status"]),
            metadata=dict(row["metadata"]),
            agent_id=agent_code_from_database_id(row["agent_id"]),
        )

    def save_task_result(self, record: TaskResultRecord) -> None:
        """在验证会话、运行和主体归属后保存统一任务结果。"""
        with self._pool.connection() as connection:
            with connection.transaction():
                user_id = self._resolve_user_id(connection, record.user_id, create=False)
                if user_id is None:
                    raise ConversationAccessDeniedError()
                database_agent_id = agent_database_id(record.agent_id)
                context = connection.execute(
                    """
                    SELECT 1
                    FROM conversations AS conversations
                    JOIN agent_runs AS runs
                      ON runs.conversation_id = conversations.conversation_id
                    WHERE conversations.conversation_id = %s
                      AND conversations.owner_id = %s
                      AND conversations.agent_id = %s
                      AND runs.run_id = %s
                      AND runs.agent_id = %s
                    """,
                    (
                        to_database_id(record.conversation_id),
                        user_id,
                        database_agent_id,
                        to_database_id(record.run_id),
                        database_agent_id,
                    ),
                ).fetchone()
                if context is None:
                    raise ConversationAccessDeniedError()
                cursor = connection.execute(
                    """
                    INSERT INTO task_results (
                        task_result_id, agent_id, user_id, conversation_id, run_id,
                        message_id, result_type, generation_status, input_data,
                        result_data
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (task_result_id) DO UPDATE SET
                        generation_status = EXCLUDED.generation_status,
                        input_data = EXCLUDED.input_data,
                        result_data = EXCLUDED.result_data,
                        message_id = COALESCE(EXCLUDED.message_id, task_results.message_id),
                        updated_at = NOW()
                    WHERE task_results.user_id = EXCLUDED.user_id
                      AND task_results.agent_id = EXCLUDED.agent_id
                      AND task_results.conversation_id = EXCLUDED.conversation_id
                      AND task_results.run_id = EXCLUDED.run_id
                    """,
                    (
                        to_database_id(record.task_result_id),
                        database_agent_id,
                        user_id,
                        to_database_id(record.conversation_id),
                        to_database_id(record.run_id),
                        to_database_id(record.message_id) if record.message_id else None,
                        record.result_type,
                        record.generation_status.value,
                        Jsonb(record.input_data),
                        Jsonb(record.result_data),
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConversationAccessDeniedError()

    def set_task_result_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool:
        """只更新结果状态；失败细节不单独持久化。"""
        with self._pool.connection() as connection:
            database_user_id = self._resolve_user_id(connection, user_id, create=False)
            if database_user_id is None:
                return False
            cursor = connection.execute(
                """
                UPDATE task_results
                SET generation_status = %s, updated_at = NOW()
                WHERE task_result_id = %s AND user_id = %s
                """,
                (
                    status.value,
                    to_database_id(task_result_id),
                    database_user_id,
                ),
            )
            return cursor.rowcount == 1

    def link_task_result_message(
        self,
        task_result_id: str,
        message_id: str,
        user_id: str,
    ) -> None:
        """仅更新任务结果的助手消息关联，不改变生成状态。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                UPDATE task_results
                SET message_id = %s, updated_at = NOW()
                WHERE task_result_id = %s AND user_id = %s
                """,
                (
                    to_database_id(message_id),
                    to_database_id(task_result_id),
                    self._resolve_user_id(connection, user_id, create=False),
                ),
            )

    def get_task_result(
        self,
        task_result_id: str,
        user_id: str,
    ) -> TaskResultRecord | None:
        """按可信用户读取任务结果及 OSS 对象元数据。"""
        with self._pool.connection() as connection:
            database_user_id = self._resolve_user_id(connection, user_id, create=False)
            if database_user_id is None:
                return None
            row = connection.execute(
                """
                SELECT task_results.*, identities.external_principal
                FROM task_results
                JOIN conversations USING (conversation_id)
                JOIN user_identities AS identities ON identities.user_id = task_results.user_id
                WHERE task_results.task_result_id = %s
                  AND task_results.user_id = %s
                  AND conversations.owner_id = %s
                """,
                (
                    to_database_id(task_result_id),
                    database_user_id,
                    database_user_id,
                ),
            ).fetchone()
        return self._task_result_from_row(row) if row is not None else None

    def list_task_results_for_messages(
        self,
        conversation_id: str,
        message_ids: list[str],
        user_id: str,
    ) -> list[TaskResultRecord]:
        """按会话、消息标识和可信用户读取任务结果元数据。"""
        if not message_ids:
            return []
        with self._pool.connection() as connection:
            database_user_id = self._resolve_user_id(connection, user_id, create=False)
            if database_user_id is None:
                return []
            rows = connection.execute(
                """
                SELECT task_results.task_result_id, task_results.agent_id,
                       task_results.user_id, task_results.conversation_id,
                       task_results.run_id, task_results.message_id,
                       task_results.result_type, task_results.generation_status,
                       task_results.input_data,
                       task_results.result_data, task_results.created_at,
                       task_results.updated_at,
                       identities.external_principal
                FROM task_results
                JOIN user_identities AS identities ON identities.user_id = task_results.user_id
                WHERE task_results.conversation_id = %s
                  AND task_results.user_id = %s
                  AND task_results.message_id = ANY(%s)
                ORDER BY task_results.created_at
                """,
                (
                    to_database_id(conversation_id),
                    database_user_id,
                    [to_database_id(message_id) for message_id in message_ids],
                ),
            ).fetchall()
        return [self._task_result_from_row(row) for row in rows]

    @staticmethod
    def _task_result_from_row(row: dict[str, Any]) -> TaskResultRecord:
        """将 PostgreSQL 行转换为内部任务结果记录。"""
        return TaskResultRecord(
            task_result_id=str(row["task_result_id"]),
            agent_id=agent_code_from_database_id(row["agent_id"]),
            user_id=row["external_principal"],
            conversation_id=str(row["conversation_id"]),
            run_id=str(row["run_id"]),
            message_id=str(row["message_id"]) if row["message_id"] is not None else None,
            result_type=row["result_type"],
            generation_status=TaskResultStatus(row["generation_status"]),
            input_data=dict(row["input_data"] or {}),
            result_data=dict(row["result_data"] or {}),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )



class PostgresConversationStore:
    """会话所有权元数据的 PostgreSQL 协议适配器。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """复用运行数据存储的连接池。"""
        self._store = store

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """持久化会话所有权元数据。"""
        self._store.save(conversation_id, metadata)

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """读取会话所有权元数据。"""
        return self._store.get(conversation_id)

    def set_title_if_empty(self, conversation_id: str, title: str) -> None:
        """为首次对话设置默认标题，不覆盖用户后续标题。"""
        self._store.set_conversation_title_if_empty(conversation_id, title)

    def list_by_owner(
        self, principal_id: str, limit: int, offset: int
    ) -> list[ConversationRecord]:
        """读取当前主体的会话列表。"""
        return self._store.list_conversations(principal_id, limit, offset)


class PostgresRunStore:
    """运行状态及追问恢复信息的 PostgreSQL 协议适配器。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """复用运行数据存储的连接池。"""
        self._store = store

    def save(self, record: RunRecord) -> None:
        """持久化运行状态变更。"""
        self._store.save_run(record)

    def get(self, run_id: str) -> RunRecord | None:
        """读取指定运行记录。"""
        return self._store.get_run(run_id)


class PostgresMessageStore:
    """会话消息表的 PostgreSQL 适配器。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """复用运行数据存储的连接池。"""
        self._store = store

    def save(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> str:
        """保存一条会话消息并返回消息标识。"""
        return self._store.save_message(conversation_id, run_id, role, content)

    def list_by_conversation(
        self,
        conversation_id: str,
        limit: int,
        before_sequence: int | None,
    ) -> list[MessageRecord]:
        """读取指定会话最新的一页消息。"""
        return self._store.list_messages(conversation_id, limit, before_sequence)


class PostgresTaskResultStore:
    """统一任务结果的 PostgreSQL 协议适配器。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """复用 Agent runtime 的 PostgreSQL 连接池。"""
        self._store = store

    def save(self, record: TaskResultRecord) -> None:
        """保存或更新一个智能体结果。"""
        self._store.save_task_result(record)

    def set_status(
        self,
        task_result_id: str,
        user_id: str,
        status: TaskResultStatus,
    ) -> bool:
        """更新结果生命周期状态。"""
        return self._store.set_task_result_status(
            task_result_id,
            user_id,
            status,
        )

    def link_message(self, task_result_id: str, message_id: str, user_id: str) -> None:
        """将生成结果与助手最终回复关联。"""
        self._store.link_task_result_message(task_result_id, message_id, user_id)

    def get_owned(self, task_result_id: str, user_id: str) -> TaskResultRecord | None:
        """按可信用户读取结果和图片字节。"""
        return self._store.get_task_result(task_result_id, user_id)

    def list_for_messages(
        self,
        conversation_id: str,
        message_ids: list[str],
        user_id: str,
    ) -> list[TaskResultRecord]:
        """按消息标识读取结果元数据，不加载图片字节。"""
        return self._store.list_task_results_for_messages(
            conversation_id,
            message_ids,
            user_id,
        )



class PostgresRunLock:
    """使用 PostgreSQL 会话级 advisory lock 协调跨进程的同会话运行。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """注入共享连接池，并保存运行期间占用的数据库连接。"""
        self._store = store
        self._connections: dict[str, Connection[Any]] = {}
        self._connections_lock = Lock()

    async def acquire(self, conversation_id: str) -> None:
        """非阻塞获取会话锁；已有其他运行时返回稳定忙碌错误。"""
        await asyncio.to_thread(self._acquire_sync, conversation_id)

    def _acquire_sync(self, conversation_id: str) -> None:
        """在线程池中获取连接并持有数据库级会话锁。"""
        connection = self._store._pool.getconn()
        try:
            row = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
                (conversation_id,),
            ).fetchone()
        except Exception:
            self._store._pool.putconn(connection)
            raise
        if not row["acquired"]:
            self._store._pool.putconn(connection)
            raise RunBusyError()
        with self._connections_lock:
            if conversation_id in self._connections:
                connection.execute(
                    "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                    (conversation_id,),
                )
                self._store._pool.putconn(connection)
                raise RunBusyError()
            self._connections[conversation_id] = connection

    def release(self, conversation_id: str) -> None:
        """释放会话锁并将连接归还连接池。"""
        with self._connections_lock:
            connection = self._connections.pop(conversation_id, None)
        if connection is None:
            return
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (conversation_id,),
            )
        finally:
            self._store._pool.putconn(connection)
