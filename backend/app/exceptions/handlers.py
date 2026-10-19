"""将 Agent 领域异常转换为稳定的 HTTP 错误响应。"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.errors import AgentError, UnknownAgentError
from agent.errors import LiteratureDocumentNotFoundError, LiteratureQueueUnavailableError
from infra.object_storage import ObjectStorageError, ObjectStorageNotConfiguredError
from infra.literature_document_storage import (
    LiteratureStorageError,
    LiteratureStorageNotConfiguredError,
)


def register_exception_handlers(app: FastAPI) -> None:
    """注册应用级业务异常转换器，保持现有错误响应结构。"""

    @app.exception_handler(AgentError)
    async def handle_agent_error(request: Request, error: AgentError) -> JSONResponse:
        """把预期 Agent 异常映射为机器可读的冲突响应。"""
        del request
        status_code = {
            "CONVERSATION_ACCESS_DENIED": 404,
            "RUN_NOT_FOUND": 404,
            "EVENT_CURSOR_INVALID": 400,
            "EVENT_STREAM_EXPIRED": 410,
            "RUN_ALREADY_ENDED": 410,
            "EVENT_STORE_UNAVAILABLE": 503,
            "AGENT_QUEUE_UNAVAILABLE": 503,
        }.get(error.code, 409)
        return JSONResponse(
            status_code=status_code,
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

    @app.exception_handler(LiteratureDocumentNotFoundError)
    async def handle_missing_literature_document(
        request: Request, error: LiteratureDocumentNotFoundError
    ) -> JSONResponse:
        """文献不存在或越权访问统一返回 404，避免泄露文献是否存在。"""
        del request
        return JSONResponse(
            status_code=404,
            content={"success": False, "code": error.code, "message": error.message},
        )

    @app.exception_handler(LiteratureQueueUnavailableError)
    async def handle_literature_queue_failure(
        request: Request, error: LiteratureQueueUnavailableError
    ) -> JSONResponse:
        """队列故障返回服务不可用，并隐藏 Broker 连接详情。"""
        del request
        return JSONResponse(
            status_code=503,
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

    @app.exception_handler(LiteratureStorageNotConfiguredError)
    async def handle_unconfigured_literature_storage(
        request: Request, error: LiteratureStorageNotConfiguredError
    ) -> JSONResponse:
        """文献 PDF 所需 OSS 未配置时返回服务不可用。"""
        del request
        return JSONResponse(
            status_code=503,
            content={"success": False, "code": "LITERATURE_STORAGE_NOT_CONFIGURED", "message": str(error)},
        )

    @app.exception_handler(LiteratureStorageError)
    async def handle_literature_storage_failure(
        request: Request, error: LiteratureStorageError
    ) -> JSONResponse:
        """文献 OSS 读写失败时不暴露上游异常细节。"""
        del request, error
        return JSONResponse(
            status_code=502,
            content={
                "success": False,
                "code": "LITERATURE_STORAGE_FAILED",
                "message": "文献文件存储暂时不可用，请稍后重试",
            },
        )
