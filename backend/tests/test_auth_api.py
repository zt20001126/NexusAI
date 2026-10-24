"""邮箱认证路由的 Cookie、会话和来源校验契约测试。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.service.auth import AuthResult
from bootstrap.application import create_app
from infra.settings import AppSettings


class FakeAuthService:
    """为认证 HTTP 测试提供可撤销的内存会话。"""

    def __init__(self) -> None:
        self.active_tokens: set[str] = set()
        self.login_calls: list[tuple[str, str]] = []

    def login(self, email: str, password: str) -> AuthResult:
        self.login_calls.append((email, password))
        self.active_tokens.add("opaque-test-token")
        return AuthResult(email=email, session_token="opaque-test-token")

    def get_session_principal(self, token: str | None) -> str | None:
        if token in self.active_tokens:
            return "user@example.test"
        return None

    def logout(self, token: str | None) -> None:
        if token:
            self.active_tokens.discard(token)


class FakeCreditService:
    """为认证路由提供可预测的余额查询。"""

    def get_balance(self, _email: str) -> int:
        return 42


def _client() -> tuple[TestClient, FakeAuthService]:
    auth_service = FakeAuthService()
    settings = AppSettings(_env_file=None)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.auth_service = auth_service
        app.state.credit_service = FakeCreditService()
        yield

    application = create_app(settings, lifespan=lifespan)
    return TestClient(application), auth_service


def test_login_sets_http_only_cookie_and_exposes_session_email() -> None:
    client, service = _client()
    with client:
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.test", "password": "a secure password"},
        )

        assert response.status_code == 200
        cookie_header = response.headers["set-cookie"].lower()
        assert "httponly" in cookie_header
        assert "samesite=lax" in cookie_header
        assert "secure" not in cookie_header
        assert client.get("/api/auth/session").json()["data"] == {
            "authenticated": True,
            "email": "user@example.test",
            "credits": 42,
        }

        logout = client.post("/api/auth/logout")
        assert logout.status_code == 200
        assert client.get("/api/auth/session").json()["data"]["authenticated"] is False
        assert service.active_tokens == set()


def test_auth_state_change_rejects_cross_origin_request() -> None:
    client, service = _client()
    with client:
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.test", "password": "a secure password"},
            headers={"Origin": "https://attacker.example"},
        )

    assert response.status_code == 403
    assert service.login_calls == []


def test_auth_state_change_accepts_origin_forwarded_by_frontend_proxy() -> None:
    client, service = _client()
    with client:
        response = client.post(
            "/api/auth/login",
            json={"email": "user@example.test", "password": "a secure password"},
            headers={
                "Origin": "http://localhost:5173",
                "X-Forwarded-Host": "localhost:5173",
            },
        )

    assert response.status_code == 200
    assert service.login_calls == [("user@example.test", "a secure password")]
