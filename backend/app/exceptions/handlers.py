"""将 Agent 领域异常转换为稳定的 HTTP 错误响应。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.errors import AgentError


def register_exception_handlers(app: FastAPI) -> None:
    """注册应用级业务异常转换器，保持现有错误响应结构。"""

    @app.exception_handler(AgentError)
    async def handle_agent_error(request: Request, error: AgentError) -> JSONResponse:
        """把预期 Agent 异常映射为机器可读的冲突响应。"""
        del request
        return JSONResponse(
            status_code=409,
            content={"success": False, "code": error.code, "message": error.message},
        )
