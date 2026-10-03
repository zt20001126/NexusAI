"""应用运行时组装与资源生命周期管理。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agent.persistence.memory import MemoryEventBus, MemoryEventSequence
from agent.persistence.postgres import PostgresEventBus, PostgresRuntimeStore
from agent.runner import build_memory_runner, build_postgres_runner
from agent.streaming.publisher import EventPublisher
from app.service.agent import AgentApplicationService
from infra.model_provider import ChatModelProvider
from infra.settings import AppSettings


def build_lifespan(
    settings: AppSettings,
    model_provider: ChatModelProvider | None,
) -> Callable[[FastAPI], Any]:
    """创建应用 lifespan，按配置装配 Agent runtime 与持久化资源。"""

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        """启动时创建运行组件，退出时释放数据库和 Checkpoint 连接。"""
        if settings.checkpoint_backend == "postgres":
            if settings.database_url is None:
                raise ValueError("使用 PostgreSQL 时必须配置 DATABASE_URL")
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

            async with AsyncPostgresSaver.from_conn_string(
                settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
            ) as checkpointer:
                await checkpointer.setup()
                with PostgresRuntimeStore(settings.database_url) as runtime_store:
                    runner = build_postgres_runner(
                        settings,
                        checkpointer=checkpointer,
                        runtime_store=runtime_store,
                        model_provider=model_provider,
                    )
                    _install_runtime_state(
                        app_instance,
                        settings,
                        runner,
                        PostgresEventBus(runtime_store),
                        runtime_store,
                    )
                    yield
        else:
            runner = build_memory_runner(settings, model_provider=model_provider)
            _install_runtime_state(
                app_instance,
                settings,
                runner,
                MemoryEventBus(),
                MemoryEventSequence(),
            )
            yield

    return lifespan


def _install_runtime_state(
    app_instance: FastAPI,
    settings: AppSettings,
    runner: Any,
    event_bus: Any,
    event_sequence: Any,
) -> None:
    """将运行时依赖注册到请求上下文，供 Controller 依赖注入使用。"""
    publisher = EventPublisher(event_bus, event_sequence, settings.sse_heartbeat_seconds)
    app_instance.state.settings = settings
    app_instance.state.agent_runner = runner
    app_instance.state.event_bus = event_bus
    app_instance.state.agent_service = AgentApplicationService(runner, publisher)
