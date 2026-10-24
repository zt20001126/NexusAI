"""编排充值尝试、Stripe Checkout 和积分到账。"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.credit_constants import MAX_CREDIT_BALANCE
from app.crud.topups import CreditTopUpRecord, PostgresCreditTopUpRepository
from app.service.credits import CreditApplicationService
from infra.settings import AppSettings
from infra.snowflake import to_database_id
from infra.stripe_checkout import StripeCheckoutGateway

logger = logging.getLogger(__name__)
MAX_STRIPE_CARD_AMOUNT = 999_999_999_999
ZERO_DECIMAL_CURRENCIES = frozenset(
    {
        "bif", "clp", "djf", "gnf", "jpy", "kmf", "krw", "mga", "pyg",
        "rwf", "vnd", "vuv", "xaf", "xof", "xpf",
    }
)
@dataclass(frozen=True)
class TopUpCurrency:
    currency: str
    minimum_amount: int
    maximum_amount: int


@dataclass(frozen=True)
class TopUpResult:
    top_up_id: str
    currency: str
    amount: int
    status: str
    checkout_url: str | None


class TopUpApplicationError(Exception):
    """充值用例可安全返回给客户端的错误。"""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CreditTopUpApplicationService:
    """协调充值账务仓储、Stripe 适配器和余额缓存。"""

    def __init__(
        self,
        repository: PostgresCreditTopUpRepository,
        gateway: StripeCheckoutGateway,
        credit_service: CreditApplicationService,
        settings: AppSettings,
    ) -> None:
        self._repository = repository
        self._gateway = gateway
        self._credit_service = credit_service
        self._settings = settings

    def list_options(self) -> list[TopUpCurrency]:
        if not self._gateway.payments_configured:
            return []
        try:
            raw_limits = json.loads(self._settings.stripe_topup_currency_limits)
        except (TypeError, json.JSONDecodeError):
            logger.error("Stripe top-up currency limits are invalid JSON")
            return []
        if not isinstance(raw_limits, dict):
            return []
        options = []
        for currency, limits in sorted(raw_limits.items()):
            if not isinstance(currency, str) or not re.fullmatch(r"[a-z]{3}", currency):
                continue
            if not isinstance(limits, dict):
                continue
            minimum, maximum = limits.get("min"), limits.get("max")
            if (
                isinstance(minimum, bool)
                or not isinstance(minimum, int)
                or isinstance(maximum, bool)
                or not isinstance(maximum, int)
                or minimum < 1
                or maximum < minimum
                or maximum * self._stripe_multiplier(currency) > MAX_STRIPE_CARD_AMOUNT
            ):
                continue
            options.append(TopUpCurrency(currency, minimum, maximum))
        return options

    def create_checkout(
        self,
        principal_id: str,
        currency: str,
        amount: int,
        request_id: str,
    ) -> TopUpResult:
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TopUpApplicationError(
                "TOP_UP_AMOUNT_OUT_OF_RANGE", "充值金额必须是正整数", 422
            )
        options = {item.currency: item for item in self.list_options()}
        option = options.get(currency)
        if option is None:
            raise TopUpApplicationError(
                "TOP_UP_CURRENCY_UNAVAILABLE", "所选支付币种暂不可用", 422
            )
        if amount < option.minimum_amount or amount > option.maximum_amount:
            raise TopUpApplicationError(
                "TOP_UP_AMOUNT_OUT_OF_RANGE",
                f"充值金额需在 {option.minimum_amount} 至 {option.maximum_amount} {currency.upper()} 之间",
                422,
            )
        multiplier = self._stripe_multiplier(currency)
        stripe_amount = amount * multiplier
        if stripe_amount > MAX_STRIPE_CARD_AMOUNT:
            raise TopUpApplicationError(
                "TOP_UP_AMOUNT_OUT_OF_RANGE", "充值金额超出支付范围", 422
            )
        try:
            top_up, _created = self._repository.create_or_get(
                principal_id, request_id, currency, amount, stripe_amount
            )
        except LookupError:
            raise TopUpApplicationError("CREDIT_ACCOUNT_NOT_FOUND", "积分账号不存在", 404) from None

        if (top_up.currency, top_up.amount, top_up.stripe_amount) != (
            currency,
            amount,
            stripe_amount,
        ):
            raise TopUpApplicationError(
                "TOP_UP_REQUEST_CONFLICT", "充值请求标识已用于其他金额", 409
            )
        if top_up.status != "pending" or top_up.checkout_url:
            return self._to_result(top_up)

        try:
            session = self._gateway.create_checkout(
                top_up_id=top_up.top_up_id,
                currency=currency,
                stripe_amount=stripe_amount,
                credits=amount,
                return_base_url=self._settings.stripe_topup_return_base_url.rstrip("/"),
            )
            top_up = self._repository.attach_checkout(
                top_up.top_up_id, session.session_id, session.checkout_url
            )
        except Exception as error:
            logger.warning(
                "Stripe Checkout creation failed top_up_id=%s error_type=%s",
                top_up.top_up_id,
                type(error).__name__,
            )
            raise TopUpApplicationError(
                "PAYMENT_PROVIDER_UNAVAILABLE", "支付服务暂不可用，请稍后重试", 503
            ) from None
        return self._to_result(top_up)

    def get_status(self, principal_id: str, top_up_id: str) -> TopUpResult:
        try:
            to_database_id(top_up_id)
            top_up = self._repository.get_for_user(principal_id, top_up_id)
        except ValueError:
            top_up = None
        if top_up is None:
            raise TopUpApplicationError("TOP_UP_NOT_FOUND", "充值记录不存在", 404)
        return self._to_result(top_up)

    def process_webhook(self, event: dict[str, Any]) -> None:
        if event.get("livemode") is not False:
            raise ValueError("仅接受 Stripe 沙盒事件")
        event_type = event.get("type")
        session = event.get("session")
        if not isinstance(session, dict):
            return
        if event_type not in {
            "checkout.session.completed",
            "checkout.session.async_payment_succeeded",
            "checkout.session.async_payment_failed",
            "checkout.session.expired",
        }:
            return
        metadata = session.get("metadata")
        top_up_id = metadata.get("top_up_id") if isinstance(metadata, dict) else None
        if (
            not isinstance(top_up_id, str)
            or not top_up_id.isascii()
            or not top_up_id.isdecimal()
        ):
            logger.warning("Ignoring Stripe event without a valid top-up reference")
            return
        session_id = session.get("id")
        currency = session.get("currency")
        stripe_amount = session.get("amount_total")
        if not isinstance(session_id, str) or not isinstance(currency, str):
            logger.warning("Ignoring incomplete Stripe checkout event")
            return
        if session.get("livemode") is not False or session.get("mode") != "payment":
            logger.warning("Ignoring non-test or non-payment Stripe session")
            return
        if session.get("client_reference_id") != top_up_id:
            logger.warning("Ignoring Stripe session with a mismatched client reference")
            return
        if isinstance(stripe_amount, bool) or not isinstance(stripe_amount, int):
            logger.warning("Ignoring Stripe event without an integer total")
            return

        if event_type in {"checkout.session.completed", "checkout.session.async_payment_succeeded"}:
            payment_status = session.get("payment_status")
            if payment_status != "paid":
                return
            new_status = "paid"
        elif event_type == "checkout.session.async_payment_failed":
            new_status = "failed"
        else:
            new_status = "expired"

        try:
            snapshot = self._repository.apply_payment_event(
                top_up_id=top_up_id,
                session_id=session_id,
                currency=currency,
                stripe_amount=stripe_amount,
                status=new_status,
            )
        except ValueError:
            logger.error("Stripe event did not match top-up top_up_id=%s", top_up_id)
            return
        except LookupError:
            logger.exception("Stripe event references an incomplete top-up top_up_id=%s", top_up_id)
            raise
        if snapshot is not None:
            self._credit_service.publish_snapshot(snapshot)

    @staticmethod
    def _to_result(top_up: CreditTopUpRecord) -> TopUpResult:
        return TopUpResult(
            top_up_id=top_up.top_up_id,
            currency=top_up.currency,
            amount=top_up.amount,
            status=top_up.status,
            checkout_url=top_up.checkout_url if top_up.status == "pending" else None,
        )

    @staticmethod
    def _stripe_multiplier(currency: str) -> int:
        if currency in ZERO_DECIMAL_CURRENCIES:
            return 1
        # This also preserves Stripe's two-decimal API representation for ISK and UGX.
        return 100
