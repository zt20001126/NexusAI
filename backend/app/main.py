"""FastAPI 应用入口，负责组装接口与全局异常处理。"""

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from app.controller.agent import router as agent_router
from app.controller.conversation import router as conversation_router
from app.exceptions.handlers import register_exception_handlers
from app.lifecycle import build_lifespan
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
        title="通用智能体基础框架",
        version="0.1.0",
        lifespan=lifespan or build_lifespan(resolved_settings, model_provider),
    )
    app.include_router(agent_router)
    app.include_router(conversation_router)
    register_exception_handlers(app)
    return app


app = create_app()
