"""封装 Stripe 测试模式 Checkout Session 与 Webhook 签名验证。"""

from dataclasses import dataclass
from typing import Any

import stripe

from infra.settings import AppSettings


@dataclass(frozen=True)
class StripeCheckoutSession:
    session_id: str
    checkout_url: str


class StripeWebhookVerificationError(Exception):
    """Stripe Webhook 原文或签名无效。"""


class StripeCheckoutGateway:
    """使用隔离的 StripeClient，拒绝 live key 和 live webhook。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    @property
    def payments_configured(self) -> bool:
        secret_key = self._settings.stripe_secret_key.get_secret_value()
        webhook_secret = self._settings.stripe_webhook_secret.get_secret_value()
        return (
            secret_key.startswith("sk_test_")
            and webhook_secret.startswith("whsec_")
            and bool(self._settings.stripe_topup_currency_limits)
        )

    def create_checkout(
        self,
        *,
        top_up_id: str,
        currency: str,
        stripe_amount: int,
        credits: int,
        return_base_url: str,
    ) -> StripeCheckoutSession:
        if not self.payments_configured:
            raise RuntimeError("Stripe sandbox credentials are not configured")
        client = self._client()
        success_url = f"{return_base_url}/#/topup?top_up_id={top_up_id}&checkout=success"
        cancel_url = f"{return_base_url}/#/topup?top_up_id={top_up_id}&checkout=cancelled"
        session = client.v1.checkout.sessions.create(
            params={
                "mode": "payment",
                "line_items": [
                    {
                        "quantity": 1,
                        "price_data": {
                            "currency": currency,
                            "unit_amount": stripe_amount,
                            "product_data": {
                                "name": f"NexusAI {credits} 积分",
                                "description": f"充值 {credits} 积分",
                            },
                        },
                    }
                ],
                "client_reference_id": top_up_id,
                "metadata": {"top_up_id": top_up_id},
                "success_url": success_url,
                "cancel_url": cancel_url,
            },
            options={"idempotency_key": f"nexusai-top-up-{top_up_id}"},
        )
        if not session.id or not session.url:
            raise RuntimeError("Stripe did not return an active Checkout URL")
        return StripeCheckoutSession(str(session.id), str(session.url))

    def construct_event(self, payload: bytes, signature: str | None) -> dict[str, Any]:
        if not self.payments_configured:
            raise RuntimeError("Stripe sandbox credentials are not configured")
        try:
            event = self._client().construct_event(
                payload,
                signature,
                self._settings.stripe_webhook_secret.get_secret_value(),
            )
        except (ValueError, stripe.SignatureVerificationError):
            raise StripeWebhookVerificationError() from None
        event_data = event.to_dict()
        data = event_data.get("data", {})
        checkout_session = data.get("object") if isinstance(data, dict) else None
        return {
            "id": event_data.get("id"),
            "type": event_data.get("type"),
            "livemode": event_data.get("livemode"),
            "session": checkout_session,
        }

    def _client(self) -> stripe.StripeClient:
        return stripe.StripeClient(
            self._settings.stripe_secret_key.get_secret_value(),
            max_network_retries=2,
        )
