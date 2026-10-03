"""PostgreSQL 持久化适配器，保存会话、消息和 Agent 运行记录。"""

import asyncio
from threading import Lock
from typing import Any
from uuid import uuid4

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from agent.schemas.run import RunRecord, RunStatus
from agent.errors import RunBusyError


class PostgresRuntimeStore:
    """集中管理会话、消息和运行记录的 PostgreSQL 连接池。"""

    def __init__(self, database_url: str) -> None:
        """创建连接池；连接串由配置层提供，不在此处读取环境变量。"""
        normalized_url = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        self._pool = ConnectionPool(
            conninfo=normalized_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True, "row_factory": dict_row},
        )

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
            CREATE TABLE IF NOT EXISTS conversations (
                conversation_id TEXT PRIMARY KEY,
                owner_id TEXT NOT NULL,
                title TEXT,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
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
                message_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                run_id TEXT REFERENCES agent_runs(run_id) ON DELETE SET NULL,
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
        )
        with self._pool.connection() as connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute("COMMENT ON TABLE conversations IS '智能体对话会话'")
            connection.execute("COMMENT ON TABLE messages IS '会话中的用户消息和助手回复'")
            connection.execute("COMMENT ON TABLE agent_runs IS '智能体运行状态与恢复信息'")

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """新增或更新会话所有者。"""
        owner_id = metadata.get("principal_id")
        if not isinstance(owner_id, str) or not owner_id:
            raise ValueError("会话必须包含有效 owner_id")
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO conversations (conversation_id, owner_id)
                VALUES (%s, %s)
                ON CONFLICT (conversation_id) DO UPDATE
                SET owner_id = EXCLUDED.owner_id, updated_at = NOW()
                """,
                (conversation_id, owner_id),
            )

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """按会话标识读取元数据副本。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT owner_id FROM conversations WHERE conversation_id = %s",
                (conversation_id,),
            ).fetchone()
        return {"principal_id": row["owner_id"]} if row is not None else None

    def save_message(
        self,
        conversation_id: str,
        run_id: str,
        role: str,
        content: str,
    ) -> None:
        """按会话锁分配消息序号并持久化消息。"""
        with self._pool.connection() as connection:
            with connection.transaction():
                conversation = connection.execute(
                    "SELECT 1 FROM conversations WHERE conversation_id = %s FOR UPDATE",
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    raise ValueError("保存消息前必须先创建会话")
                sequence = connection.execute(
                    """
                    SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
                    FROM messages WHERE conversation_id = %s
                    """,
                    (conversation_id,),
                ).fetchone()["next_sequence"]
                connection.execute(
                    """
                    INSERT INTO messages (
                        message_id, conversation_id, run_id, sequence, role, content
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (uuid4().hex, conversation_id, run_id, sequence, role, content),
                )
                connection.execute(
                    "UPDATE conversations SET updated_at = NOW() WHERE conversation_id = %s",
                    (conversation_id,),
                )

    def save_run(self, record: RunRecord) -> None:
        """持久化新增或更新的智能体运行记录。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, conversation_id, status, metadata
                ) VALUES (%s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    conversation_id = EXCLUDED.conversation_id,
                    status = EXCLUDED.status,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                (
                    record.run_id,
                    record.conversation_id,
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
                       runs.status, runs.metadata
                FROM agent_runs AS runs
                JOIN conversations USING (conversation_id)
                WHERE runs.run_id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row["run_id"],
            conversation_id=row["conversation_id"],
            principal_id=row["owner_id"],
            status=RunStatus(row["status"]),
            metadata=dict(row["metadata"]),
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
    ) -> None:
        """保存一条会话消息。"""
        self._store.save_message(conversation_id, run_id, role, content)


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
