"""HTTP 层可信身份及后续鉴权集成接缝。"""

from fastapi import HTTPException, Request, status


def get_principal_id(request: Request) -> str:
    """从有效服务端会话取得主体标识，不接受客户端身份字段。"""
    principal_id = getattr(request.state, "principal_id", None)
    if isinstance(principal_id, str) and principal_id:
        return principal_id
    settings = request.app.state.settings
    token = request.cookies.get(settings.auth_cookie_name)
    principal_id = request.app.state.auth_service.get_session_principal(token)
    if isinstance(principal_id, str) and principal_id:
        return principal_id
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="请先登录",
    )
