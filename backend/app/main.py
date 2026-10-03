"""通用智能体 FastAPI 应用工厂。"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from agent.errors import AgentError
from agent.persistence.memory import MemoryEventBus, MemoryEventSequence
from agent.persistence.postgres import PostgresEventBus, PostgresRuntimeStore
from agent.runner import build_memory_runner, build_postgres_runner
from agent.streaming.publisher import EventPublisher
from app.routes import router
from app.service import AgentApplicationService
from infra.model_provider import ChatModelProvider
from infra.settings import AppSettings
from typing import Any

logger = logging.getLogger(__name__)


def create_app(
    settings: AppSettings | None = None,
    model_provider: ChatModelProvider | None = None,
) -> FastAPI:
    """创建独立应用并注册默认示例智能体。

    默认使用 DeepSeek Provider；只在应用 lifespan 组装模型，不在模块导入
    阶段建立网络连接。测试和离线场景可注入替代 Provider。
    """
    resolved_settings = settings or AppSettings()

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        """按配置创建持久化资源，并在应用关闭时释放连接。"""
        if resolved_settings.checkpoint_backend == "postgres":
            if resolved_settings.database_url is None:
                raise ValueError("使用 PostgreSQL 时必须配置 DATABASE_URL")
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(
                resolved_settings.database_url.replace(
                    "postgresql+psycopg://", "postgresql://", 1
                )
            ) as checkpointer:
                await checkpointer.setup()
                with PostgresRuntimeStore(resolved_settings.database_url) as runtime_store:
                    runner = build_postgres_runner(
                        resolved_settings,
                        checkpointer=checkpointer,
                        runtime_store=runtime_store,
                        model_provider=model_provider,
                    )
                    event_bus = PostgresEventBus(runtime_store)
                    _install_runtime_state(
                        app_instance,
                        resolved_settings,
                        runner,
                        event_bus,
                        runtime_store,
                    )
                    yield
        else:
            runner = build_memory_runner(resolved_settings, model_provider=model_provider)
            event_bus = MemoryEventBus()
            _install_runtime_state(
                app_instance,
                resolved_settings,
                runner,
                event_bus,
                MemoryEventSequence(),
            )
            yield

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


def _install_runtime_state(
    app_instance: FastAPI,
    settings: AppSettings,
    runner: Any,
    event_bus: Any,
    event_sequence: Any,
) -> None:
    """将本应用共享运行组件注册到 FastAPI 生命周期状态。"""
    publisher = EventPublisher(
        event_bus,
        event_sequence,
        settings.sse_heartbeat_seconds,
    )
    app_instance.state.settings = settings
    app_instance.state.agent_runner = runner
    app_instance.state.event_bus = event_bus
    app_instance.state.agent_service = AgentApplicationService(runner, publisher)


app = create_app()
