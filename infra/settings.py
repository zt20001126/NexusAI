"""集中管理应用、模型和可选基础设施配置。"""

from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用配置。

    默认后端均为内存或禁用，因此开发环境不需要运行 PostgreSQL、Redis
    或 Celery；只有显式启用相应后端时才校验连接配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_host: str = "127.0.0.1"
    app_port: int = Field(default=8000, ge=1, le=65535)

    llm_provider: str = "openai_compatible"
    llm_model: str = ""
    llm_api_key: SecretStr = SecretStr("")
    llm_base_url: str = ""
    llm_timeout_seconds: int = Field(default=60, ge=1, le=600)

    checkpoint_backend: Literal["memory", "postgres"] = "memory"
    database_url: str | None = None
    lock_backend: Literal["memory", "redis"] = "memory"
    event_bus_backend: Literal["memory", "redis"] = "memory"
    redis_url: str | None = None
    task_backend: Literal["disabled", "celery"] = "disabled"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    agent_max_steps: int = Field(default=20, ge=2, le=100)
    agent_max_tool_calls: int = Field(default=20, ge=1, le=100)
    agent_max_output_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    agent_run_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=60)

    @model_validator(mode="after")
    def validate_enabled_backends(self) -> Self:
        """仅对显式启用的外部后端要求连接配置。"""
        if self.checkpoint_backend == "postgres" and not self.database_url:
            raise ValueError("启用 PostgreSQL Checkpoint 时必须配置 DATABASE_URL")
        if (
            self.lock_backend == "redis" or self.event_bus_backend == "redis"
        ) and not self.redis_url:
            raise ValueError("启用 Redis 后端时必须配置 REDIS_URL")
        if self.task_backend == "celery" and not self.celery_broker_url:
            raise ValueError("启用 Celery 时必须配置 CELERY_BROKER_URL")
        return self
