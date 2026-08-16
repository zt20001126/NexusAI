"""HTTP 层可信身份及后续鉴权集成接缝。"""

from fastapi import Request


def get_principal_id(request: Request) -> str:
    """从服务端请求上下文取得主体标识。

    独立开发模式固定使用本地主体，不接受客户端 `user_id`。接入现有用户系统时，
    应由认证中间件写入 `request.state.principal_id`，无需修改 Service 或 Runtime。
    """
    principal_id = getattr(request.state, "principal_id", None)
    if isinstance(principal_id, str) and principal_id:
        return principal_id
    return "local-development"

