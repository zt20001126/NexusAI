"""集中管理应用、模型和基础设施配置。"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """应用配置。

    统一管理模型、数据库和智能体运行限制。应用运行时始终使用 PostgreSQL，
    DATABASE_URL 是唯一的应用数据库连接配置；本地运行时指向 localhost，
    Compose 网络内由服务配置覆盖为 postgres 主机名。内存适配器只供测试代码显式使用。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: int = Field(default=60, ge=1, le=600)

    tencent_cloud_secret_id: SecretStr = SecretStr("")
    tencent_cloud_secret_key: SecretStr = SecretStr("")
    tencent_hunyuan_image_region: str = "ap-guangzhou"
    tencent_hunyuan_image_endpoint: str = "https://aiart.tencentcloudapi.com"
    tencent_hunyuan_image_api_version: str = "2022-12-29"
    tencent_hunyuan_image_action: str = "TextToImageLite"

    volcengine_ark_api_key: SecretStr = SecretStr("")
    volcengine_ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_seedream_model: str = "doubao-seedream-5-0-flash-260915"

    database_url: str | None = None

    agent_max_steps: int = Field(default=20, ge=2, le=100)
    agent_max_tool_calls: int = Field(default=20, ge=1, le=100)
    agent_max_output_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    agent_run_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=60)
