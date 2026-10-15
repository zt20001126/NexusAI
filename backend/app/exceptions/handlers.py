"""将 Agent 领域异常转换为稳定的 HTTP 错误响应。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.errors import AgentError, UnknownAgentError
from infra.object_storage import ObjectStorageError, ObjectStorageNotConfiguredError


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

    @app.exception_handler(UnknownAgentError)
    async def handle_unknown_agent(request: Request, error: UnknownAgentError) -> JSONResponse:
        """未注册智能体使用标准 404，便于客户端区分资源不存在。"""
        del request
        return JSONResponse(
            status_code=404,
            content={"success": False, "code": error.code, "message": error.message},
        )

    @app.exception_handler(ObjectStorageNotConfiguredError)
    async def handle_unconfigured_storage(
        request: Request,
        error: ObjectStorageNotConfiguredError,
    ) -> JSONResponse:
        """OSS 未配置时返回稳定服务不可用响应。"""
        del request
        return JSONResponse(
            status_code=503,
            content={
                "success": False,
                "code": "OBJECT_STORAGE_NOT_CONFIGURED",
                "message": str(error),
            },
        )

    @app.exception_handler(ObjectStorageError)
    async def handle_storage_failure(
        request: Request,
        error: ObjectStorageError,
    ) -> JSONResponse:
        """OSS 读写失败时不暴露上游错误细节。"""
        del request, error
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "code": "OBJECT_STORAGE_FAILED",
                "message": "图片存储暂时不可用，请稍后重试",
            },
        )
