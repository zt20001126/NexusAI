"""使用 Redis TTL 保存一次性邮箱验证码和短期浏览器会话。"""

import hashlib

from redis import Redis
from redis.exceptions import RedisError

from infra.settings import AppSettings


CODE_RESEND_SECONDS = 60
AUTH_STORE_TIMEOUT_SECONDS = 3

_ISSUE_CODE_SCRIPT = """
if redis.call('EXISTS', KEYS[2]) == 1 then
    return 0
end
redis.call('SET', KEYS[2], '1', 'EX', ARGV[3])
redis.call('HSET', KEYS[1], 'digest', ARGV[1], 'failed_attempts', '0')
redis.call('EXPIRE', KEYS[1], ARGV[2])
return 1
"""

_VERIFY_CODE_SCRIPT = """
local code_digest = redis.call('HGET', KEYS[1], 'digest')
if not code_digest then
    return 0
end
if code_digest ~= ARGV[1] then
    local attempts = redis.call('HINCRBY', KEYS[1], 'failed_attempts', 1)
    if attempts >= tonumber(ARGV[2]) then
        redis.call('DEL', KEYS[1])
    end
    return 0
end
redis.call('DEL', KEYS[1])
return 1
"""


class AuthStoreUnavailableError(Exception):
    """认证 Redis 状态暂时不可用。"""


class RedisAuthStore:
    """以原子 Lua 操作管理验证码尝试、冷却和可撤销 Cookie 会话。"""

    def __init__(self, settings: AppSettings) -> None:
        self._redis = Redis.from_url(
            settings.celery_broker_url,
            decode_responses=True,
            socket_connect_timeout=AUTH_STORE_TIMEOUT_SECONDS,
            socket_timeout=AUTH_STORE_TIMEOUT_SECONDS,
        )

    def issue_code(
        self,
        *,
        email: str,
        purpose: str,
        code_digest: str,
        ttl_seconds: int,
    ) -> bool:
        """创建有过期时间的验证码，并原子设置邮箱用途冷却键。"""
        try:
            return bool(
                self._redis.eval(
                    _ISSUE_CODE_SCRIPT,
                    2,
                    self._code_key(email, purpose),
                    self._cooldown_key(email, purpose),
                    code_digest,
                    ttl_seconds,
                    CODE_RESEND_SECONDS,
                )
            )
        except RedisError as error:
            raise AuthStoreUnavailableError() from error

    def verify_code(
        self,
        *,
        email: str,
        purpose: str,
        code_digest: str,
        max_attempts: int,
    ) -> bool:
        """在同一 Redis 操作内累计失败次数或一次性消费验证码。"""
        try:
            return bool(
                self._redis.eval(
                    _VERIFY_CODE_SCRIPT,
                    1,
                    self._code_key(email, purpose),
                    code_digest,
                    max_attempts,
                )
            )
        except RedisError as error:
            raise AuthStoreUnavailableError() from error

    def delete_code(self, email: str, purpose: str) -> None:
        """邮件发送失败时删除验证码，保留重发冷却。"""
        try:
            self._redis.delete(self._code_key(email, purpose))
        except RedisError as error:
            raise AuthStoreUnavailableError() from error

    def create_session(
        self,
        *,
        token: str,
        email: str,
        password_hash: str,
        ttl_seconds: int,
    ) -> None:
        """保存高熵 Cookie token 对应的邮箱和当前密码指纹。"""
        value = f"{email}\n{_password_fingerprint(password_hash)}"
        try:
            self._redis.set(self._session_key(token), value, ex=ttl_seconds)
        except RedisError as error:
            raise AuthStoreUnavailableError() from error

    def get_session(self, token: str) -> tuple[str, str] | None:
        """查询有效 Cookie 对应的邮箱与密码指纹。"""
        try:
            value = self._redis.get(self._session_key(token))
        except RedisError as error:
            raise AuthStoreUnavailableError() from error
        if not value:
            return None
        email, separator, fingerprint = value.partition("\n")
        if not separator or not email or len(fingerprint) != 64:
            return None
        return email, fingerprint

    def revoke_session(self, token: str) -> None:
        """删除当前 Cookie 对应的会话，使其立即失效。"""
        try:
            self._redis.delete(self._session_key(token))
        except RedisError as error:
            raise AuthStoreUnavailableError() from error

    def close(self) -> None:
        """释放同步 Redis 连接池。"""
        self._redis.close()

    @staticmethod
    def _code_key(email: str, purpose: str) -> str:
        return f"nexusai:auth:code:{purpose}:{email}"

    @staticmethod
    def _cooldown_key(email: str, purpose: str) -> str:
        return f"nexusai:auth:cooldown:{purpose}:{email}"

    @staticmethod
    def _session_key(token: str) -> str:
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        return f"nexusai:auth:session:{digest}"


def _password_fingerprint(password_hash: str) -> str:
    """标记签发会话时的密码凭据版本，不暴露密码哈希本身。"""
    return hashlib.sha256(password_hash.encode("utf-8")).hexdigest()
