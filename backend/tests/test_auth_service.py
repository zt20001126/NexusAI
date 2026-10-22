"""认证用例的密码哈希、验证码、会话和邮件失败边界测试。"""

import hashlib

import pytest

from app.crud.auth import AuthUser
from app.service.auth import (
    AuthApplicationError,
    AuthApplicationService,
    hash_password,
    normalize_email,
    verify_password,
)
from infra.settings import AppSettings


class FakeAuthRepository:
    """模拟现有 users 表中的邮箱账号和密码哈希。"""

    def __init__(self) -> None:
        self.user: AuthUser | None = None

    def get_user(self, email: str) -> AuthUser | None:
        return self.user if self.user and self.user.account == email else None

    def create_user(self, email: str, password_hash: str) -> bool:
        if self.user is not None:
            return False
        self.user = AuthUser(1, email, password_hash)
        return True

    def update_password(self, email: str, password_hash: str) -> bool:
        if self.user is None or self.user.account != email:
            return False
        self.user = AuthUser(self.user.user_id, email, password_hash)
        return True


class FakeAuthStore:
    """模拟 Redis 中带 TTL 的验证码与会话状态。"""

    def __init__(self) -> None:
        self.codes: dict[tuple[str, str], tuple[str, int]] = {}
        self.cooldowns: set[tuple[str, str]] = set()
        self.sessions: dict[str, tuple[str, str]] = {}
        self.rate_limited = False

    def issue_code(self, *, email: str, purpose: str, code_digest: str, ttl_seconds: int) -> bool:
        key = (email, purpose)
        if self.rate_limited or key in self.cooldowns:
            return False
        self.codes[key] = (code_digest, 0)
        self.cooldowns.add(key)
        return True

    def verify_code(self, *, email: str, purpose: str, code_digest: str, max_attempts: int) -> bool:
        key = (email, purpose)
        saved = self.codes.get(key)
        if saved is None:
            return False
        if saved[0] != code_digest:
            attempts = saved[1] + 1
            if attempts >= max_attempts:
                self.codes.pop(key, None)
            else:
                self.codes[key] = (saved[0], attempts)
            return False
        self.codes.pop(key, None)
        return True

    def delete_code(self, email: str, purpose: str) -> None:
        self.codes.pop((email, purpose), None)

    def create_session(self, *, token: str, email: str, password_hash: str, ttl_seconds: int) -> None:
        fingerprint = hashlib.sha256(password_hash.encode("utf-8")).hexdigest()
        self.sessions[token] = (email, fingerprint)

    def get_session(self, token: str) -> tuple[str, str] | None:
        return self.sessions.get(token)

    def revoke_session(self, token: str) -> None:
        self.sessions.pop(token, None)


class FakeEmailSender:
    """在测试内记录投递内容并可模拟 SMTP 失败。"""

    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.messages: list[tuple[str, str, str, str]] = []

    def send(self, recipient: str, subject: str, text_body: str, html_body: str) -> None:
        self.messages.append((recipient, subject, text_body, html_body))
        if self.fail:
            from infra.email_sender import EmailDeliveryError

            raise EmailDeliveryError("SMTP credential must not leak")


def _service(*, fail_delivery: bool = False):
    settings = AppSettings(
        _env_file=None,
        auth_code_pepper="test-code-pepper-value",
        mail_smtp_username="nexus@example.test",
        mail_smtp_password="smtp-secret",
    )
    repository = FakeAuthRepository()
    auth_store = FakeAuthStore()
    sender = FakeEmailSender(fail=fail_delivery)
    service = AuthApplicationService(
        repository=repository,
        auth_store=auth_store,
        email_sender=sender,
        settings=settings,
    )
    return service, repository, sender, auth_store


def test_password_hash_uses_salt_and_rejects_wrong_password() -> None:
    first = hash_password("correct horse")
    second = hash_password("correct horse")

    assert first != second
    assert verify_password("correct horse", first)
    assert not verify_password("wrong password", first)


def test_email_normalization_is_case_insensitive() -> None:
    assert normalize_email(" User@Example.COM ") == "user@example.com"


@pytest.mark.asyncio
async def test_registration_code_uses_template_and_creates_user_session(monkeypatch) -> None:
    service, repository, sender, _ = _service()
    monkeypatch.setattr("app.service.auth.secrets.randbelow", lambda _: 0)

    await service.request_email_code("User@example.test", "register")
    result = service.register("USER@example.test", "000000", "a secure password")

    assert sender.messages[0][0] == "user@example.test"
    assert "注册验证码" in sender.messages[0][1]
    assert "000000" in sender.messages[0][2]
    assert repository.user is not None
    assert service.get_session_principal(result.session_token) == "user@example.test"


@pytest.mark.asyncio
async def test_unknown_reset_request_is_accepted_without_sending_email() -> None:
    service, _, sender, _ = _service()

    await service.request_email_code("unknown@example.test", "password_reset")

    assert sender.messages == []


@pytest.mark.asyncio
async def test_reset_delivery_failure_does_not_reveal_registered_email() -> None:
    service, repository, _, auth_store = _service(fail_delivery=True)
    repository.user = AuthUser(1, "user@example.test", hash_password("existing password"))

    await service.request_email_code("user@example.test", "password_reset")

    assert auth_store.codes == {}


@pytest.mark.asyncio
async def test_reset_cooldown_does_not_reveal_registered_email() -> None:
    service, repository, sender, auth_store = _service()
    repository.user = AuthUser(1, "user@example.test", hash_password("existing password"))
    auth_store.rate_limited = True

    await service.request_email_code("user@example.test", "password_reset")

    assert sender.messages == []


@pytest.mark.asyncio
async def test_password_reset_invalidates_old_sessions_through_password_fingerprint(monkeypatch) -> None:
    service, repository, _, _ = _service()
    repository.user = AuthUser(1, "user@example.test", hash_password("old password"))
    monkeypatch.setattr("app.service.auth.secrets.randbelow", lambda _: 0)
    old_session = service.login("user@example.test", "old password")
    await service.request_email_code("user@example.test", "password_reset")

    service.reset_password("user@example.test", "000000", "new secure password")

    assert service.get_session_principal(old_session.session_token) is None
    with pytest.raises(AuthApplicationError) as error:
        service.login("user@example.test", "old password")
    assert error.value.code == "INVALID_CREDENTIALS"
    assert service.login("user@example.test", "new secure password").email == "user@example.test"


@pytest.mark.asyncio
async def test_smtp_failure_returns_controlled_error_and_removes_unsent_code() -> None:
    service, _, _, auth_store = _service(fail_delivery=True)

    with pytest.raises(AuthApplicationError) as error:
        await service.request_email_code("user@example.test", "register")

    assert error.value.code == "EMAIL_DELIVERY_FAILED"
    assert "SMTP credential" not in error.value.message
    assert auth_store.codes == {}
