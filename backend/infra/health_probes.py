"""PostgreSQL 和 Redis Broker 的轻量健康探针适配器。"""

from psycopg import AsyncConnection
from redis.asyncio import Redis


class PostgresHealthProbe:
    """通过独立异步连接执行 SELECT 1，验证应用配置的 PostgreSQL 可达。"""

    name = "postgres"

    def __init__(self, database_url: str, timeout_seconds: int) -> None:
        """接收配置层提供的 DSN 和连接时限，不读取环境变量。"""
        self._database_url = database_url.replace(
            "postgresql+psycopg://", "postgresql://", 1
        )
        self._timeout_seconds = timeout_seconds

    async def check(self) -> None:
        """连接数据库并执行轻量查询；连接异常交由巡检器记录。"""
        async with await AsyncConnection.connect(
            conninfo=self._database_url,
            connect_timeout=self._timeout_seconds,
        ) as connection:
            await connection.execute("SELECT 1")


class RedisBrokerHealthProbe:
    """通过项目配置的 Redis Broker 执行 PING，并在应用关闭时释放连接池。"""

    name = "redis"

    def __init__(self, broker_url: str, timeout_seconds: int) -> None:
        """从 Celery Broker 配置创建受超时约束的异步 Redis 客户端。"""
        self._client = Redis.from_url(
            broker_url,
            socket_connect_timeout=timeout_seconds,
            socket_timeout=timeout_seconds,
        )

    async def check(self) -> None:
        """向 Redis Broker 发送 PING，确认当前应用能够访问消息代理。"""
        await self._client.ping()

    async def aclose(self) -> None:
        """关闭异步 Redis 连接池，避免应用重载或退出时遗留连接。"""
        await self._client.aclose()
