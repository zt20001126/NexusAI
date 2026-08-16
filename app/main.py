"""通用智能体 FastAPI 应用工厂。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent_core.errors import AgentFrameworkError
from agent_core.runtime.factory import build_runtime
from agents.example_agent.definition import create_example_agent_definition
from app.routes import router
from app.service import AgentApplicationService
from infra.settings import AppSettings

logger = logging.getLogger(__name__)


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """创建独立应用并注册默认示例智能体。

    默认工厂只初始化内存资源。未来外部后端应在 lifespan 中建立并关闭
    连接，不得在模块导入阶段产生网络副作用。
    """
    resolved_settings = settings or AppSettings()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        """在应用生命周期内创建共享运行资源并预留统一关闭位置。"""
        runtime = build_runtime(resolved_settings)
        runtime.register(create_example_agent_definition())
        app_instance.state.settings = resolved_settings
        app_instance.state.agent_runtime = runtime
        app_instance.state.agent_service = AgentApplicationService(
            runtime,
            resolved_settings.sse_heartbeat_seconds,
        )
        yield
        # 内存实现无需显式关闭；未来连接池、Redis 和任务客户端在此统一释放。

    app = FastAPI(
        title="通用智能体基础框架",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(AgentFrameworkError)
    async def handle_agent_error(
        request: Request,
        error: AgentFrameworkError,
    ) -> JSONResponse:
        """将可预期业务异常映射为安全、机器可读的 HTTP 响应。"""
        del request
        status_code = 404 if error.code == "AGENT_NOT_FOUND" else 409
        return JSONResponse(
            status_code=status_code,
            content={"success": False, "code": error.code, "message": error.message},
        )

    return app


app = create_app()
