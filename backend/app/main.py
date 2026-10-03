"""FastAPI 应用入口，负责组装接口与全局异常处理。"""

from fastapi import FastAPI

from app.controller.agent import router
from app.exceptions.handlers import register_exception_handlers
from app.lifecycle import build_lifespan
from infra.model_provider import ChatModelProvider
from infra.settings import AppSettings


def create_app(
    settings: AppSettings | None = None,
    model_provider: ChatModelProvider | None = None,
) -> FastAPI:
    """创建应用并注入配置、运行时生命周期和 API 路由。"""
    resolved_settings = settings or AppSettings()
    app = FastAPI(
        title="通用智能体基础框架",
        version="0.1.0",
        lifespan=build_lifespan(resolved_settings, model_provider),
    )
    app.include_router(router)
    register_exception_handlers(app)
    return app


app = create_app()
