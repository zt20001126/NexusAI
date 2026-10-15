"""创建 SQLAlchemy PostgreSQL 引擎和短生命周期 ORM 会话。"""

from typing import Self

from psycopg_pool import ConnectionPool
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator


class PostgresDatabase:
    """应用数据库资源，负责引擎、Session 工厂及 ORM 表结构初始化。"""

    def __init__(
        self,
        database_url: str,
        id_generator: SnowflakeIdGenerator | None = None,
    ) -> None:
        """使用配置层提供的 PostgreSQL URL 创建连接池和会话工厂。"""
        normalized_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
        self.engine: Engine = create_engine(
            normalized_url,
            pool_size=10,
            max_overflow=0,
            pool_pre_ping=True,
        )
        lock_database_url = normalized_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        self.run_lock_pool = ConnectionPool(
            conninfo=lock_database_url,
            min_size=1,
            max_size=10,
            open=False,
            kwargs={"autocommit": True},
        )
        self.session_factory: sessionmaker[Session] = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
        )
        self.id_generator = id_generator or get_snowflake_generator()

    def __enter__(self) -> Self:
        """启动时按 ORM 元数据创建缺失表，不修改已有表结构。"""
        try:
            # pgvector 必须先注册扩展类型，后续 ORM 才能创建向量列。
            with self.engine.begin() as connection:
                connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            Base.metadata.create_all(self.engine)
            self.run_lock_pool.open(wait=True)
        except Exception:
            self.run_lock_pool.close()
            self.engine.dispose()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        """应用关闭时释放 ORM 引擎和 advisory lock 连接池。"""
        self.run_lock_pool.close()
        self.engine.dispose()
