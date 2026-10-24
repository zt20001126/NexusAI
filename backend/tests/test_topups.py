"""积分充值金额、Checkout 和 Webhook 用例测试。"""

from dataclasses import dataclass

import pytest
from pydantic import SecretStr

from app.crud.credits import CreditBalanceSnapshot
from app.crud.topups import CreditTopUpRecord
from app.service.topups import (
    CreditTopUpApplicationService,
    TopUpApplicationError,
)
from infra.settings import AppSettings
from infra.stripe_checkout import StripeCheckoutSession


@dataclass
class MemoryTopUpRepository:
    record: CreditTopUpRecord | None = None
    event_status: str | None = None

    def create_or_get(self, principal_id, request_id, currency, amount, stripe_amount):
        if self.record is None:
            self.record = CreditTopUpRecord(
                top_up_id="123456",
                user_id=12,
                principal_id=principal_id,
                request_id=request_id,
                currency=currency,
                amount=amount,
                stripe_amount=stripe_amount,
                stripe_session_id=None,
                checkout_url=None,
                status="pending",
            )
            return self.record, True
        return self.record, False

    def attach_checkout(self, top_up_id, session_id, checkout_url):
        assert top_up_id == self.record.top_up_id
        self.record = CreditTopUpRecord(
            **{
                **self.record.__dict__,
                "stripe_session_id": session_id,
                "checkout_url": checkout_url,
            }
        )
        return self.record

    def get_for_user(self, principal_id, top_up_id):
        if self.record and self.record.principal_id == principal_id:
            return self.record
        return None

    def apply_payment_event(self, **kwargs):
        self.event_status = kwargs["status"]
        return CreditBalanceSnapshot("user@example.test", 12, 125, 4) if kwargs["status"] == "paid" else None


class FakeStripeGateway:
    payments_configured = True

    def __init__(self):
        self.create_calls = []

    def create_checkout(self, **kwargs):
        self.create_calls.append(kwargs)
        return StripeCheckoutSession("cs_test_example", "https://checkout.stripe.com/test")


class FakeCreditService:
    def __init__(self):
        self.snapshots = []

    def publish_snapshot(self, snapshot):
        self.snapshots.append(snapshot)


def _service():
    settings = AppSettings(
        _env_file=None,
        stripe_secret_key=SecretStr("sk_test_example"),
        stripe_webhook_secret=SecretStr("whsec_example"),
        stripe_topup_currency_limits=(
            '{"usd":{"min":1,"max":1000},"jpy":{"min":50,"max":1000},'
            '"isk":{"min":5,"max":1000},"ugx":{"min":5,"max":1000}}'
        ),
    )
    repository = MemoryTopUpRepository()
    gateway = FakeStripeGateway()
    credits = FakeCreditService()
    service = CreditTopUpApplicationService(repository, gateway, credits, settings)
    return service, repository, gateway, credits


def test_checkout_converts_major_amount_to_stripe_minor_units() -> None:
    service, repository, gateway, _ = _service()

    result = service.create_checkout("user@example.test", "usd", 10, "request-12345678")

    assert result.amount == 10
    assert result.status == "pending"
    assert result.checkout_url == "https://checkout.stripe.com/test"
    assert repository.record.stripe_amount == 1000
    assert gateway.create_calls[0]["stripe_amount"] == 1000


def test_zero_decimal_currency_uses_same_stripe_amount() -> None:
    service, repository, gateway, _ = _service()

    service.create_checkout("user@example.test", "jpy", 50, "request-12345678")

    assert repository.record.stripe_amount == 50
    assert gateway.create_calls[0]["stripe_amount"] == 50


@pytest.mark.parametrize("currency", ["isk", "ugx"])
def test_legacy_zero_decimal_currency_uses_two_decimal_api_amount(currency: str) -> None:
    service, repository, gateway, _ = _service()

    service.create_checkout("user@example.test", currency, 5, "request-12345678")

    assert repository.record.stripe_amount == 500
    assert gateway.create_calls[0]["stripe_amount"] == 500


def test_checkout_rejects_amount_below_configured_currency_minimum() -> None:
    service, _, gateway, _ = _service()

    with pytest.raises(TopUpApplicationError) as error:
        service.create_checkout("user@example.test", "jpy", 10, "request-12345678")

    assert error.value.code == "TOP_UP_AMOUNT_OUT_OF_RANGE"
    assert gateway.create_calls == []


def test_checkout_rejects_currency_outside_configured_allowlist() -> None:
    service, _, gateway, _ = _service()

    with pytest.raises(TopUpApplicationError) as error:
        service.create_checkout("user@example.test", "cad", 10, "request-12345678")

    assert error.value.code == "TOP_UP_CURRENCY_UNAVAILABLE"
    assert gateway.create_calls == []


def test_webhook_credits_only_paid_matching_test_session() -> None:
    service, repository, _, credits = _service()
    service.create_checkout("user@example.test", "usd", 10, "request-12345678")
    event = {
        "livemode": False,
        "type": "checkout.session.completed",
        "session": {
            "id": "cs_test_example",
            "livemode": False,
            "mode": "payment",
            "client_reference_id": "123456",
            "currency": "usd",
            "amount_total": 1000,
            "payment_status": "paid",
            "metadata": {"top_up_id": "123456"},
        },
    }

    service.process_webhook(event)

    assert repository.event_status == "paid"
    assert len(credits.snapshots) == 1
    assert credits.snapshots[0].balance == 125


def test_webhook_does_not_credit_unpaid_checkout() -> None:
    service, repository, _, credits = _service()
    event = {
        "livemode": False,
        "type": "checkout.session.completed",
        "session": {
            "id": "cs_test_example",
            "livemode": False,
            "mode": "payment",
            "client_reference_id": "123456",
            "currency": "usd",
            "amount_total": 1000,
            "payment_status": "unpaid",
            "metadata": {"top_up_id": "123456"},
        },
    }

    service.process_webhook(event)

    assert repository.event_status is None
    assert credits.snapshots == []
