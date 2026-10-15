"""应用组装入口，负责创建 FastAPI 实例并注册接口与异常处理。"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from app.exceptions.handlers import register_exception_handlers
from app.router.agent import router as agent_router
from app.router.agents import router as agents_router
from app.router.conversation import router as conversation_router
from bootstrap.runtime import build_lifespan
from infra.model_provider import ChatModelProvider
from infra.settings import AppSettings


def create_app(
    settings: AppSettings | None = None,
    model_provider: ChatModelProvider | None = None,
    *,
    lifespan: Callable[[FastAPI], Any] | None = None,
) -> FastAPI:
    """创建应用；默认连接 PostgreSQL，lifespan 可由测试显式注入。"""
    resolved_settings = settings or AppSettings()
    app = FastAPI(
        title="NexusAI 多智能体工作台",
        version="0.1.0",
        lifespan=lifespan or build_lifespan(resolved_settings, model_provider),
    )
    app.include_router(agent_router)
    app.include_router(agents_router)
    app.include_router(conversation_router)
    register_exception_handlers(app)
    return app


app = create_app()
