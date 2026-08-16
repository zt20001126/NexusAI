"""通用智能体 FastAPI 应用工厂。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.errors import AgentError
from agent.persistence.memory import MemoryEventBus, MemoryEventSequence
from agent.runner import build_memory_runner
from agent.streaming.publisher import EventPublisher
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
        runner = build_memory_runner(resolved_settings)
        event_bus = MemoryEventBus()
        publisher = EventPublisher(
            event_bus,
            MemoryEventSequence(),
            resolved_settings.sse_heartbeat_seconds,
        )
        app_instance.state.settings = resolved_settings
        app_instance.state.agent_runner = runner
        app_instance.state.event_bus = event_bus
        app_instance.state.agent_service = AgentApplicationService(
            runner,
            publisher,
        )
        yield
        # 内存实现无需显式关闭；未来连接池、Redis 和任务客户端在此统一释放。

    app = FastAPI(
        title="通用智能体基础框架",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.include_router(router)

    @app.exception_handler(AgentError)
    async def handle_agent_error(
        request: Request,
        error: AgentError,
    ) -> JSONResponse:
        """将可预期业务异常映射为安全、机器可读的 HTTP 响应。"""
        del request
        status_code = 409
        return JSONResponse(
            status_code=status_code,
            content={"success": False, "code": error.code, "message": error.message},
        )

    return app


app = create_app()
