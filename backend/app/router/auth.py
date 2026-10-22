"""邮箱注册、登录、验证码及密码重置 HTTP 接口。"""

from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request, Response

from app.schemas.auth import (
    EmailCodeRequest,
    LoginRequest,
    PasswordResetRequest,
    RegisterRequest,
)
from app.service.auth import AuthApplicationError

router = APIRouter(prefix="/api/auth", tags=["账号认证"])


def _success(data: dict) -> dict:
    return {"success": True, "data": data}


def _set_session_cookie(response: Response, request: Request, token: str) -> None:
    settings = request.app.state.settings
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.secure_auth_cookie,
        samesite="lax",
        path="/",
    )


def _clear_session_cookie(response: Response, request: Request) -> None:
    settings = request.app.state.settings
    response.delete_cookie(
        key=settings.auth_cookie_name,
        httponly=True,
        secure=settings.secure_auth_cookie,
        samesite="lax",
        path="/",
    )


def _validate_origin(request: Request) -> None:
    """当浏览器提供 Origin 时，拒绝跨站认证状态变更请求。"""
    origin = request.headers.get("origin")
    if not origin:
        return
    try:
        origin_host = urlsplit(origin).netloc.casefold()
    except ValueError:
        origin_host = ""
    # 本地 Vite 代理及生产反向代理需转发浏览器侧 Host；直接请求仍校验 Host。
    request_host = request.headers.get(
        "x-forwarded-host", request.headers.get("host", "")
    ).casefold()
    if not origin_host or origin_host != request_host:
        raise HTTPException(status_code=403, detail="请求来源不受信任")


@router.post("/email-codes")
async def request_email_code(payload: EmailCodeRequest, request: Request) -> dict:
    _validate_origin(request)
    await request.app.state.auth_service.request_email_code(
        payload.email,
        payload.purpose,
    )
    return _success({"requested": True})


@router.post("/register")
def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
) -> dict:
    _validate_origin(request)
    result = request.app.state.auth_service.register(
        payload.email,
        payload.code,
        payload.password,
    )
    _set_session_cookie(response, request, result.session_token)
    return _success({"email": result.email})


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response) -> dict:
    _validate_origin(request)
    result = request.app.state.auth_service.login(payload.email, payload.password)
    _set_session_cookie(response, request, result.session_token)
    return _success({"email": result.email})


@router.get("/session")
def get_session(request: Request) -> dict:
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    email = request.app.state.auth_service.get_session_principal(token)
    return _success({"authenticated": email is not None, "email": email})


@router.post("/logout")
def logout(request: Request, response: Response) -> dict:
    _validate_origin(request)
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    request.app.state.auth_service.logout(token)
    _clear_session_cookie(response, request)
    return _success({"logged_out": True})


@router.post("/password-reset")
def reset_password(
    payload: PasswordResetRequest,
    request: Request,
    response: Response,
) -> dict:
    _validate_origin(request)
    request.app.state.auth_service.reset_password(
        payload.email,
        payload.code,
        payload.new_password,
    )
    _clear_session_cookie(response, request)
    return _success({"password_reset": True})
