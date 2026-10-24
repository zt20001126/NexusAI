"""Stripe Checkout 适配器测试。"""

from types import SimpleNamespace

import infra.stripe_checkout as stripe_checkout
import stripe
from pydantic import SecretStr

from infra.settings import AppSettings
from infra.stripe_checkout import StripeCheckoutGateway


def test_checkout_uses_dashboard_payment_method_configuration(monkeypatch) -> None:
    class FakeCheckoutSessions:
        params: dict | None = None

        def create(self, *, params: dict, options: dict) -> SimpleNamespace:
            self.params = params
            return SimpleNamespace(id="cs_test_example", url="https://checkout.stripe.com/test")

    sessions = FakeCheckoutSessions()
    fake_client = SimpleNamespace(
        v1=SimpleNamespace(checkout=SimpleNamespace(sessions=sessions))
    )
    monkeypatch.setattr(
        stripe_checkout.stripe,
        "StripeClient",
        lambda *_args, **_kwargs: fake_client,
    )
    settings = AppSettings(
        _env_file=None,
        stripe_secret_key=SecretStr("sk_test_example"),
        stripe_webhook_secret=SecretStr("whsec_example"),
        stripe_topup_currency_limits='{"eur":{"min":1,"max":100}}',
    )

    result = StripeCheckoutGateway(settings).create_checkout(
        top_up_id="123456789012345678",
        currency="eur",
        stripe_amount=100,
        credits=1,
        return_base_url="http://localhost:5173",
    )

    assert result.session_id == "cs_test_example"
    assert result.checkout_url == "https://checkout.stripe.com/test"
    assert sessions.params is not None
    assert "payment_method_types" not in sessions.params


def test_construct_event_converts_stripe_objects_to_plain_dicts(monkeypatch) -> None:
    stripe_event = stripe.Event.construct_from(
        {
            "id": "evt_test_example",
            "object": "event",
            "type": "checkout.session.completed",
            "livemode": False,
            "data": {
                "object": {
                    "id": "cs_test_example",
                    "object": "checkout.session",
                    "mode": "payment",
                    "payment_status": "paid",
                    "client_reference_id": "123456",
                    "currency": "eur",
                    "amount_total": 100,
                    "metadata": {"top_up_id": "123456"},
                }
            },
        },
        None,
    )
    settings = AppSettings(
        _env_file=None,
        stripe_secret_key=SecretStr("sk_test_example"),
        stripe_webhook_secret=SecretStr("whsec_example"),
        stripe_topup_currency_limits='{"eur":{"min":1,"max":100}}',
    )
    gateway = StripeCheckoutGateway(settings)
    monkeypatch.setattr(
        gateway,
        "_client",
        lambda: SimpleNamespace(
            construct_event=lambda _payload, _signature, _secret: stripe_event
        ),
    )

    result = gateway.construct_event(b"{}", "valid-signature")

    assert result == {
        "id": "evt_test_example",
        "type": "checkout.session.completed",
        "livemode": False,
        "session": {
            "id": "cs_test_example",
            "object": "checkout.session",
            "mode": "payment",
            "payment_status": "paid",
            "client_reference_id": "123456",
            "currency": "eur",
            "amount_total": 100,
            "metadata": {"top_up_id": "123456"},
        },
    }
