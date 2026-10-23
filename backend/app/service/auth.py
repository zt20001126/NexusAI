"""编排邮箱验证码、账号凭据和浏览器登录会话。"""

import asyncio
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC

from app.crud.auth import PostgresAuthRepository
from app.service.credits import CreditApplicationService
from app.service.auth_email_templates import (
    render_password_reset_email,
    render_registration_email,
)
from infra.email_sender import EmailDeliveryError, SmtpEmailSender
from infra.redis_auth_store import AuthStoreUnavailableError, RedisAuthStore
from infra.settings import AppSettings


EMAIL_CODE_TTL_MINUTES = 10
EMAIL_CODE_TTL_SECONDS = EMAIL_CODE_TTL_MINUTES * 60
PASSWORD_MIN_CHARS = 8
PASSWORD_MAX_CHARS = 128
SCRYPT_COST = 16_384
SCRYPT_BLOCK_SIZE = 8
SCRYPT_PARALLELISM = 1
SCRYPT_KEY_BYTES = 32
SCRYPT_SALT_BYTES = 16
MAX_CODE_ATTEMPTS = 5


class AuthApplicationError(Exception):
    """具有稳定 HTTP 语义的认证业务错误。"""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class AuthResult:
    """认证成功后供 Router 设置 Cookie 的短期结果。"""

    email: str
    session_token: str


class AuthApplicationService:
    """执行业务认证规则，向 HTTP 层隐藏哈希与仓储细节。"""

    def __init__(
        self,
        *,
        repository: PostgresAuthRepository,
        auth_store: RedisAuthStore,
        email_sender: SmtpEmailSender,
        settings: AppSettings,
        credit_service: CreditApplicationService | None = None,
    ) -> None:
        self._repository = repository
        self._auth_store = auth_store
        self._email_sender = email_sender
        self._settings = settings
        self._credit_service = credit_service

    async def request_email_code(self, email_value: str, purpose: str) -> None:
        """发送有用途、有效期和重发冷却限制的邮箱验证码。"""
        email = normalize_email(email_value)
        if purpose not in {"register", "password_reset"}:
            raise AuthApplicationError(422, "INVALID_CODE_PURPOSE", "验证码用途无效")
        self._require_code_pepper()
        if not self._settings.mail_smtp_configured:
            raise AuthApplicationError(
                503, "EMAIL_DELIVERY_UNAVAILABLE", "邮件发送服务尚未配置"
            )
        user_exists = self._repository.get_user(email) is not None
        if purpose == "register" and user_exists:
            raise AuthApplicationError(409, "EMAIL_ALREADY_REGISTERED", "该邮箱已注册")

        if purpose == "password_reset" and not user_exists:
            # 对未知邮箱不发信，并保持与已注册邮箱一致的公开响应。
            return

        code = f"{secrets.randbelow(1_000_000):06d}"
        try:
            issued = self._auth_store.issue_code(
                email=email,
                purpose=purpose,
                code_digest=self._code_digest(email, purpose, code),
                ttl_seconds=EMAIL_CODE_TTL_SECONDS,
            )
        except AuthStoreUnavailableError:
            if purpose == "password_reset":
                return
            raise _auth_store_unavailable() from None
        if not issued:
            if purpose == "password_reset":
                return
            raise AuthApplicationError(429, "EMAIL_CODE_RATE_LIMITED", "请稍后再获取验证码")

        email_content = (
            render_registration_email(code, EMAIL_CODE_TTL_MINUTES)
            if purpose == "register"
            else render_password_reset_email(code, EMAIL_CODE_TTL_MINUTES)
        )
        try:
            await asyncio.to_thread(
                self._email_sender.send,
                email,
                email_content.subject,
                email_content.text_body,
                email_content.html_body,
            )
        except EmailDeliveryError:
            try:
                self._auth_store.delete_code(email, purpose)
            except AuthStoreUnavailableError:
                pass
            if purpose == "password_reset":
                # 找回请求不暴露邮箱是否存在或该地址的邮件投递状态。
                return
            raise AuthApplicationError(
                503, "EMAIL_DELIVERY_FAILED", "验证码邮件发送失败，请稍后重试"
            ) from None

    def register(self, email_value: str, code: str, password: str) -> AuthResult:
        """校验注册验证码并在成功后建立邮箱账号及浏览器会话。"""
        email = normalize_email(email_value)
        validate_password(password)
        self._require_code_pepper()
        self._verify_email_code(email, "register", code)
        password_hash = hash_password(password)
        if not self._repository.create_user(email, password_hash):
            raise AuthApplicationError(409, "EMAIL_ALREADY_REGISTERED", "该邮箱已注册")
        if self._credit_service is not None:
            self._credit_service.refresh(email)
        return self._create_session(email, password_hash)

    def login(self, email_value: str, password: str) -> AuthResult:
        """验证邮箱密码并签发不透明随机会话。"""
        email = normalize_email(email_value)
        user = self._repository.get_user(email)
        if user is None or not user.password_hash or not verify_password(
            password, user.password_hash
        ):
            raise AuthApplicationError(401, "INVALID_CREDENTIALS", "邮箱或密码错误")
        return self._create_session(email, user.password_hash)

    def reset_password(
        self,
        email_value: str,
        code: str,
        new_password: str,
    ) -> None:
        """消费密码找回码、更新密码并注销该账号的所有旧会话。"""
        email = normalize_email(email_value)
        validate_password(new_password)
        self._require_code_pepper()
        self._verify_email_code(email, "password_reset", code)
        if not self._repository.update_password(email, hash_password(new_password)):
            raise AuthApplicationError(400, "INVALID_EMAIL_CODE", "验证码无效或已过期")

    def get_session_principal(self, session_token: str | None) -> str | None:
        """由不透明 Cookie 查出未过期且未撤销会话的可信账号。"""
        if not session_token:
            return None
        try:
            session = self._auth_store.get_session(session_token)
        except AuthStoreUnavailableError:
            raise _auth_store_unavailable() from None
        if session is None:
            return None
        email, password_fingerprint = session
        user = self._repository.get_user(email)
        if user is None or user.password_hash is None:
            return None
        current_fingerprint = hashlib.sha256(
            user.password_hash.encode("utf-8")
        ).hexdigest()
        return email if hmac.compare_digest(password_fingerprint, current_fingerprint) else None

    def logout(self, session_token: str | None) -> None:
        """撤销当前会话；无 Cookie 时也保持幂等。"""
        if session_token:
            try:
                self._auth_store.revoke_session(session_token)
            except AuthStoreUnavailableError:
                raise _auth_store_unavailable() from None

    def _create_session(self, email: str, password_hash: str) -> AuthResult:
        token = secrets.token_urlsafe(32)
        try:
            self._auth_store.create_session(
                token=token,
                email=email,
                password_hash=password_hash,
                ttl_seconds=self._settings.auth_session_ttl_seconds,
            )
        except AuthStoreUnavailableError:
            raise _auth_store_unavailable() from None
        return AuthResult(email=email, session_token=token)

    def _verify_email_code(self, email: str, purpose: str, code: str) -> None:
        try:
            valid = self._auth_store.verify_code(
                email=email,
                purpose=purpose,
                code_digest=self._code_digest(email, purpose, code),
                max_attempts=MAX_CODE_ATTEMPTS,
            )
        except AuthStoreUnavailableError:
            raise _auth_store_unavailable() from None
        if not valid:
            raise AuthApplicationError(400, "INVALID_EMAIL_CODE", "验证码无效或已过期")

    def _code_digest(self, email: str, purpose: str, code: str) -> str:
        secret = self._settings.auth_code_pepper.get_secret_value().encode("utf-8")
        message = f"{purpose}:{email}:{code}".encode("utf-8")
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def _require_code_pepper(self) -> None:
        if not self._settings.auth_code_pepper.get_secret_value().strip():
            raise AuthApplicationError(
                503,
                "AUTH_CODE_NOT_CONFIGURED",
                "邮箱验证码服务尚未配置",
            )


def normalize_email(email: str) -> str:
    """去除邮箱首尾空白并规范化大小写，拒绝明显无效输入。"""
    normalized = email.strip().casefold()
    local, separator, domain = normalized.partition("@")
    if (
        len(normalized) > 254
        or not separator
        or not local
        or not domain
        or "." not in domain
        or any(character.isspace() for character in normalized)
    ):
        raise AuthApplicationError(422, "INVALID_EMAIL", "邮箱格式不正确")
    return normalized


def _auth_store_unavailable() -> AuthApplicationError:
    """Map Redis failures to a controlled authentication dependency error."""
    return AuthApplicationError(
        503,
        "AUTH_STATE_UNAVAILABLE",
        "认证服务暂时不可用，请稍后重试",
    )


def validate_password(password: str) -> None:
    """校验密码边界，保留用户输入中的空格。"""
    if not PASSWORD_MIN_CHARS <= len(password) <= PASSWORD_MAX_CHARS:
        raise AuthApplicationError(
            422,
            "INVALID_PASSWORD",
            f"密码长度须为 {PASSWORD_MIN_CHARS} 至 {PASSWORD_MAX_CHARS} 个字符",
        )


def hash_password(password: str) -> str:
    """用随机盐和标准库 scrypt 生成密码哈希。"""
    salt = secrets.token_bytes(SCRYPT_SALT_BYTES)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_COST,
        r=SCRYPT_BLOCK_SIZE,
        p=SCRYPT_PARALLELISM,
        dklen=SCRYPT_KEY_BYTES,
    )
    return "$".join(
        (
            "scrypt",
            str(SCRYPT_COST),
            str(SCRYPT_BLOCK_SIZE),
            str(SCRYPT_PARALLELISM),
            _b64(salt),
            _b64(digest),
        )
    )


def verify_password(password: str, password_hash: str) -> bool:
    """恒定时间比较 scrypt 哈希，格式错误时拒绝认证。"""
    try:
        algorithm, cost, block_size, parallelism, salt_value, digest_value = (
            password_hash.split("$")
        )
        if algorithm != "scrypt":
            return False
        if (
            int(cost) != SCRYPT_COST
            or int(block_size) != SCRYPT_BLOCK_SIZE
            or int(parallelism) != SCRYPT_PARALLELISM
        ):
            return False
        salt = _unb64(salt_value)
        expected = _unb64(digest_value)
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=SCRYPT_COST,
            r=SCRYPT_BLOCK_SIZE,
            p=SCRYPT_PARALLELISM,
            dklen=len(expected),
        )
    except (ValueError, TypeError, MemoryError):
        return False
    return hmac.compare_digest(actual, expected)


def _b64(value: bytes) -> str:
    import base64

    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    import base64

    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
