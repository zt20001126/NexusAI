"""充值 API 的认证、请求校验与 Webhook 边界测试。"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from app.service.topups import TopUpCurrency, TopUpResult
from bootstrap.application import create_app
from infra.settings import AppSettings


class FakeAuthService:
    def get_session_principal(self, token):
        return "user@example.test" if token == "valid-session" else None


class FakeTopUpService:
    def list_options(self):
        return [TopUpCurrency("usd", 1, 1000)]

    def create_checkout(self, principal_id, currency, amount, request_id):
        assert principal_id == "user@example.test"
        return TopUpResult("123456", currency, amount, "pending", "https://checkout.stripe.com/test")

    def get_status(self, principal_id, top_up_id):
        if principal_id != "user@example.test" or top_up_id != "123456":
            from app.service.topups import TopUpApplicationError

            raise TopUpApplicationError("TOP_UP_NOT_FOUND", "充值记录不存在", 404)
        return TopUpResult("123456", "usd", 10, "paid", None)

    def process_webhook(self, event):
        assert event == {"event": "verified"}


class FakeStripeGateway:
    def construct_event(self, payload, signature):
        assert payload == b'{"raw":true}'
        assert signature == "valid-signature"
        return {"event": "verified"}


@pytest.fixture
def client():
    settings = AppSettings(_env_file=None)
    auth_service = FakeAuthService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.settings = settings
        app.state.auth_service = auth_service
        app.state.topup_service = FakeTopUpService()
        app.state.stripe_gateway = FakeStripeGateway()
        yield

    app = create_app(settings, lifespan=lifespan)
    with TestClient(app) as test_client:
        test_client.cookies.set(settings.auth_cookie_name, "valid-session")
        yield test_client


def test_top_up_options_require_login(client: TestClient) -> None:
    client.cookies.clear()

    response = client.get("/api/credits/top-up-options")

    assert response.status_code == 401


def test_create_top_up_returns_checkout_url_for_authenticated_user(client: TestClient) -> None:
    response = client.post(
        "/api/credits/top-ups",
        json={
            "currency": "usd",
            "amount": 10,
            "request_id": "request-12345678",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"] == {
        "top_up_id": "123456",
        "currency": "usd",
        "amount": 10,
        "credits": 10,
        "status": "pending",
        "checkout_url": "https://checkout.stripe.com/test",
    }


def test_create_top_up_rejects_fractional_amount(client: TestClient) -> None:
    response = client.post(
        "/api/credits/top-ups",
        json={
            "currency": "usd",
            "amount": 10.5,
            "request_id": "request-12345678",
        },
    )

    assert response.status_code == 422


def test_create_top_up_rejects_cross_origin_request(client: TestClient) -> None:
    response = client.post(
        "/api/credits/top-ups",
        json={
            "currency": "usd",
            "amount": 10,
            "request_id": "request-12345678",
        },
        headers={"Origin": "https://attacker.example"},
    )

    assert response.status_code == 403


def test_webhook_forwards_raw_body_after_signature_verification(client: TestClient) -> None:
    response = client.post(
        "/api/stripe/webhook",
        content=b'{"raw":true}',
        headers={"Stripe-Signature": "valid-signature"},
    )

    assert response.status_code == 200
    assert response.json() == {"received": True}


def test_webhook_rejects_payload_above_size_limit(client: TestClient) -> None:
    response = client.post(
        "/api/stripe/webhook",
        content=b"x" * (1_048_576 + 1),
        headers={"Stripe-Signature": "valid-signature"},
    )

    assert response.status_code == 413
