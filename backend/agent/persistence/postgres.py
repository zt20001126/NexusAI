"""PostgreSQL 持久化适配器，保存会话、运行记录、事件和序号。"""

import asyncio
from collections.abc import AsyncIterator
from threading import Lock
from typing import Any

from psycopg import Connection
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from psycopg_pool import ConnectionPool

from agent.schemas.run import RunRecord, RunStatus
from agent.streaming.events import AgentEvent
from agent.errors import RunBusyError

EVENT_HISTORY_LIMIT = 1_000
EVENT_POLL_INTERVAL_SECONDS = 0.25


class PostgresRuntimeStore:
    """集中管理运行元数据、事件历史和序号的 PostgreSQL 连接池。"""

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

    def __enter__(self) -> PostgresRuntimeStore:
        """打开连接池并确保应用元数据表存在。"""
        self._pool.open(wait=True)
        self._create_tables()
        return self

    def __exit__(self, *_: object) -> None:
        """应用关闭时释放 PostgreSQL 连接。"""
        self._pool.close()

    def _create_tables(self) -> None:
        """初始化应用运行数据表；LangGraph 检查点由其官方适配器单独管理。"""
        statements = (
            """
            CREATE TABLE IF NOT EXISTS agent_conversations (
                conversation_id TEXT PRIMARY KEY,
                metadata JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_runs (
                run_id TEXT PRIMARY KEY,
                conversation_id TEXT NOT NULL,
                principal_id TEXT NOT NULL,
                status TEXT NOT NULL,
                metadata JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_agent_runs_conversation_id
            ON agent_runs (conversation_id)
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_event_sequences (
                conversation_id TEXT PRIMARY KEY,
                last_sequence BIGINT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS agent_events (
                conversation_id TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                event JSONB NOT NULL,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                PRIMARY KEY (conversation_id, sequence)
            )
            """,
        )
        with self._pool.connection() as connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "COMMENT ON TABLE agent_conversations IS '智能体会话所有权及元数据'"
            )
            connection.execute("COMMENT ON TABLE agent_runs IS '智能体运行状态与恢复信息'")
            connection.execute("COMMENT ON TABLE agent_event_sequences IS '会话事件游标计数器'")
            connection.execute("COMMENT ON TABLE agent_events IS '用于 SSE 断点重放的事件历史'")

    def save(self, conversation_id: str, metadata: dict[str, Any]) -> None:
        """新增或更新会话所有权元数据。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_conversations (conversation_id, metadata)
                VALUES (%s, %s)
                ON CONFLICT (conversation_id) DO UPDATE
                SET metadata = EXCLUDED.metadata, updated_at = NOW()
                """,
                (conversation_id, Jsonb(metadata)),
            )

    def get(self, conversation_id: str) -> dict[str, Any] | None:
        """按会话标识读取元数据副本。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                "SELECT metadata FROM agent_conversations WHERE conversation_id = %s",
                (conversation_id,),
            ).fetchone()
        return dict(row["metadata"]) if row is not None else None

    def save_run(self, record: RunRecord) -> None:
        """持久化新增或更新的智能体运行记录。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_runs (
                    run_id, conversation_id, principal_id, status, metadata
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    conversation_id = EXCLUDED.conversation_id,
                    principal_id = EXCLUDED.principal_id,
                    status = EXCLUDED.status,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
                """,
                (
                    record.run_id,
                    record.conversation_id,
                    record.principal_id,
                    record.status.value,
                    Jsonb(record.metadata),
                ),
            )

    def get_run(self, run_id: str) -> RunRecord | None:
        """读取运行记录并恢复为领域数据对象。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                SELECT run_id, conversation_id, principal_id, status, metadata
                FROM agent_runs WHERE run_id = %s
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return RunRecord(
            run_id=row["run_id"],
            conversation_id=row["conversation_id"],
            principal_id=row["principal_id"],
            status=RunStatus(row["status"]),
            metadata=dict(row["metadata"]),
        )

    def next(self, conversation_id: str) -> int:
        """以原子 UPSERT 为会话分配跨进程单调递增的事件序号。"""
        with self._pool.connection() as connection:
            row = connection.execute(
                """
                INSERT INTO agent_event_sequences (conversation_id, last_sequence)
                VALUES (%s, 1)
                ON CONFLICT (conversation_id) DO UPDATE
                SET last_sequence = agent_event_sequences.last_sequence + 1
                RETURNING last_sequence
                """,
                (conversation_id,),
            ).fetchone()
        return int(row["last_sequence"])

    def save_event(self, event: AgentEvent) -> None:
        """保存 SSE 事件，并为每个会话保留最近的有界历史。"""
        with self._pool.connection() as connection:
            connection.execute(
                """
                INSERT INTO agent_events (conversation_id, sequence, event)
                VALUES (%s, %s, %s)
                ON CONFLICT (conversation_id, sequence) DO NOTHING
                """,
                (event.conversation_id, event.sequence, Jsonb(event.model_dump(mode="json"))),
            )
            oldest_retained = event.sequence - EVENT_HISTORY_LIMIT
            if oldest_retained > 0:
                connection.execute(
                    """
                    DELETE FROM agent_events
                    WHERE conversation_id = %s AND sequence <= %s
                    """,
                    (event.conversation_id, oldest_retained),
                )

    def events_after(
        self,
        conversation_id: str,
        sequence: int,
    ) -> list[AgentEvent]:
        """读取游标之后的有序事件批次。"""
        with self._pool.connection() as connection:
            rows = connection.execute(
                """
                SELECT event FROM agent_events
                WHERE conversation_id = %s AND sequence > %s
                ORDER BY sequence ASC
                LIMIT %s
                """,
                (conversation_id, sequence, EVENT_HISTORY_LIMIT),
            ).fetchall()
        return [AgentEvent.model_validate(row["event"]) for row in rows]


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


class PostgresEventBus:
    """通过 PostgreSQL 保存事件并轮询新事件，支持进程重启后的游标续读。"""

    def __init__(self, store: PostgresRuntimeStore) -> None:
        """注入生命周期内共享的运行数据存储。"""
        self._store = store

    async def publish(self, event: AgentEvent) -> None:
        """在线程池中写入事件，避免同步数据库 I/O 阻塞异步流。"""
        await asyncio.to_thread(self._store.save_event, event)

    async def subscribe(
        self,
        conversation_id: str,
        after: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """先重放游标后的历史事件，再轮询并交付后续事件。"""
        sequence = self._parse_cursor(conversation_id, after)
        while True:
            events = await asyncio.to_thread(
                self._store.events_after,
                conversation_id,
                sequence,
            )
            if not events:
                await asyncio.sleep(EVENT_POLL_INTERVAL_SECONDS)
                continue
            for event in events:
                sequence = event.sequence
                yield event

    @staticmethod
    def _parse_cursor(conversation_id: str, cursor: str | None) -> int:
        """解析本会话事件 ID；无效或异会话游标从最早保留事件开始。"""
        if cursor is None:
            return 0
        cursor_conversation_id, separator, raw_sequence = cursor.rpartition(":")
        if not separator or cursor_conversation_id != conversation_id:
            return 0
        try:
            return max(int(raw_sequence), 0)
        except ValueError:
            return 0
