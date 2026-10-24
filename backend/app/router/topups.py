"""积分充值与 Stripe Webhook HTTP 边界。"""

from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.dependencies.auth import get_principal_id
from app.schemas.topups import TopUpOptionsResponse, TopUpRequest, TopUpResponse
from app.service.topups import CreditTopUpApplicationService
from infra.stripe_checkout import StripeWebhookVerificationError

router = APIRouter(tags=["积分充值"])
MAX_WEBHOOK_BYTES = 1_048_576


def _success(data: dict) -> dict:
    return {"success": True, "data": data}


def _validate_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        origin_host = urlsplit(origin).netloc.casefold()
    except ValueError:
        origin_host = ""
    request_host = request.headers.get(
        "x-forwarded-host", request.headers.get("host", "")
    ).casefold()
    if not origin_host or origin_host != request_host:
        raise HTTPException(status_code=403, detail="请求来源不受信任")


def _service(request: Request) -> CreditTopUpApplicationService:
    return request.app.state.topup_service


@router.get("/api/credits/top-up-options")
def get_top_up_options(
    request: Request,
    _principal_id: str = Depends(get_principal_id),
) -> dict:
    options = _service(request).list_options()
    return _success(
        TopUpOptionsResponse(
            currencies=[
                {
                    "currency": option.currency,
                    "minimum_amount": option.minimum_amount,
                    "maximum_amount": option.maximum_amount,
                }
                for option in options
            ]
        ).model_dump()
    )


@router.post("/api/credits/top-ups")
def create_top_up(
    payload: TopUpRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict:
    _validate_origin(request)
    result = _service(request).create_checkout(
        principal_id,
        payload.currency,
        payload.amount,
        payload.request_id,
    )
    return _success(
        TopUpResponse(
            top_up_id=result.top_up_id,
            currency=result.currency,
            amount=result.amount,
            credits=result.amount,
            status=result.status,
            checkout_url=result.checkout_url,
        ).model_dump()
    )


@router.get("/api/credits/top-ups/{top_up_id}")
def get_top_up_status(
    top_up_id: str,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict:
    result = _service(request).get_status(principal_id, top_up_id)
    return _success(
        TopUpResponse(
            top_up_id=result.top_up_id,
            currency=result.currency,
            amount=result.amount,
            credits=result.amount,
            status=result.status,
            checkout_url=result.checkout_url,
        ).model_dump()
    )


@router.post("/api/stripe/webhook")
async def stripe_webhook(request: Request) -> JSONResponse:
    content_length = request.headers.get("content-length")
    if content_length and content_length.isdecimal() and int(content_length) > MAX_WEBHOOK_BYTES:
        return JSONResponse(status_code=413, content={"detail": "Webhook 请求体过大"})
    payload_buffer = bytearray()
    async for chunk in request.stream():
        if len(payload_buffer) + len(chunk) > MAX_WEBHOOK_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Webhook 请求体过大"})
        payload_buffer.extend(chunk)
    payload = bytes(payload_buffer)
    service = _service(request)
    gateway = request.app.state.stripe_gateway
    signature = request.headers.get("stripe-signature")
    try:
        event = await run_in_threadpool(gateway.construct_event, payload, signature)
        await run_in_threadpool(service.process_webhook, event)
    except StripeWebhookVerificationError:
        return JSONResponse(status_code=400, content={"detail": "Stripe 签名无效"})
    except RuntimeError:
        return JSONResponse(status_code=503, content={"detail": "支付服务尚未配置"})
    except ValueError:
        return JSONResponse(status_code=400, content={"detail": "Stripe 事件无效"})
    return JSONResponse(status_code=200, content={"received": True})
