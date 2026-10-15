"""使用 PostgreSQL advisory lock 实现会话级跨进程运行互斥。"""

import asyncio
from threading import Lock
from typing import Any

from psycopg import Connection

from agent.errors import RunBusyError
from app.db.database import PostgresDatabase


class PostgresRunLock:
    """运行锁适配器，持有数据库会话锁直到对应智能体运行结束。"""

    def __init__(self, database: PostgresDatabase) -> None:
        """注入共享数据库资源并初始化当前进程的连接登记表。"""
        self._database = database
        self._connections: dict[str, Connection[Any]] = {}
        self._connections_lock = Lock()

    async def acquire(self, conversation_id: str) -> None:
        """在线程池中等待 PostgreSQL 立即尝试获取会话锁。"""
        await asyncio.to_thread(self._acquire_sync, conversation_id)

    def _acquire_sync(self, conversation_id: str) -> None:
        """从专用 psycopg 池获取 AUTOCOMMIT 连接并持有会话级锁。"""
        connection = self._database.run_lock_pool.getconn()
        try:
            row = connection.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s, 0)) AS acquired",
                (conversation_id,),
            ).fetchone()
        except Exception:
            self._database.run_lock_pool.putconn(connection)
            raise
        if row is None or not row[0]:
            self._database.run_lock_pool.putconn(connection)
            raise RunBusyError()

        with self._connections_lock:
            if conversation_id in self._connections:
                self._unlock(connection, conversation_id)
                raise RunBusyError()
            self._connections[conversation_id] = connection

    async def release(self, conversation_id: str) -> None:
        """在线程池中释放 PostgreSQL 会话锁并归还连接池连接。"""
        await asyncio.to_thread(self._release_sync, conversation_id)

    def _release_sync(self, conversation_id: str) -> None:
        """从持有连接的登记表移除会话并释放数据库锁。"""
        with self._connections_lock:
            connection = self._connections.pop(conversation_id, None)
        if connection is not None:
            self._unlock(connection, conversation_id)

    def _unlock(
        self,
        connection: Connection[Any],
        conversation_id: str,
    ) -> None:
        """执行 advisory unlock，并确保连接始终归还 psycopg 池。"""
        try:
            connection.execute(
                "SELECT pg_advisory_unlock(hashtextextended(%s, 0))",
                (conversation_id,),
            )
        finally:
            self._database.run_lock_pool.putconn(connection)
