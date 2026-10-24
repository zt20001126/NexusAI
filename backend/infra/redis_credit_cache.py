"""提供以 PostgreSQL 版本号保护写入顺序的 Redis 积分余额缓存。"""

import hashlib

from redis import Redis
from redis.exceptions import RedisError

from infra.settings import AppSettings


CREDIT_REDIS_TIMEOUT_SECONDS = 3
_PUBLISH_IF_NEWER = """
local current = redis.call('HGET', KEYS[1], 'version')
if current and tonumber(current) > tonumber(ARGV[2]) then
    return 0
end
redis.call('HSET', KEYS[1], 'balance', ARGV[1], 'version', ARGV[2])
return 1
"""


class CreditCacheUnavailableError(Exception):
    """Redis 积分缓存不可访问。"""


class RedisCreditCache:
    """缓存积分快照，并拒绝旧版本覆盖较新的余额状态。"""

    def __init__(self, settings: AppSettings) -> None:
        """复用应用 Redis Broker 地址，使用短超时避免阻塞提交请求。"""
        self._redis = Redis.from_url(
            settings.celery_broker_url,
            decode_responses=True,
            socket_connect_timeout=CREDIT_REDIS_TIMEOUT_SECONDS,
            socket_timeout=CREDIT_REDIS_TIMEOUT_SECONDS,
        )

    def get(self, principal_id: str) -> tuple[int, int] | None:
        """按主体读取余额及其数据库版本；缓存未命中返回 None。"""
        try:
            values = self._redis.hgetall(self._key(principal_id))
        except RedisError as error:
            raise CreditCacheUnavailableError() from error
        if not values:
            return None
        try:
            return int(values["balance"]), int(values["version"])
        except (KeyError, TypeError, ValueError) as error:
            raise CreditCacheUnavailableError() from error

    def publish(self, principal_id: str, balance: int, version: int) -> None:
        """原子比较版本后更新余额，避免启动快照或并发发布乱序覆盖。"""
        try:
            self._redis.eval(
                _PUBLISH_IF_NEWER,
                1,
                self._key(principal_id),
                balance,
                version,
            )
        except RedisError as error:
            raise CreditCacheUnavailableError() from error

    def close(self) -> None:
        """关闭 Redis 连接池。"""
        self._redis.close()

    @staticmethod
    def _key(principal_id: str) -> str:
        """用主体摘要作缓存键，避免将邮箱明文放入 Redis 键名。"""
        owner_digest = hashlib.sha256(principal_id.encode("utf-8")).hexdigest()
        return f"nexusai:credits:{owner_digest}"
