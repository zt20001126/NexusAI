"""集中管理应用、模型和基础设施配置。"""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.constants import MAX_REFERENCE_IMAGE_BYTES


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
        populate_by_name=True,
    )

    app_env: str = "development"
    # Snowflake worker ID 在同一套部署中的并发进程间必须唯一，1022/1023 为系统保留值。
    snowflake_worker_id: int = Field(default=0, ge=0, le=1021)
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

    # TokenHub 配置只影响淘宝图片智能体；未启用该智能体时密钥可以为空。
    tokenhub_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("TENCENT_TOKENHUB_API_KEY", "tokenhub_api_key"),
    )
    tokenhub_base_url: str = Field(
        default="https://tokenhub.tencentmaas.com",
        validation_alias=AliasChoices("TENCENT_TOKENHUB_BASE_URL", "tokenhub_base_url"),
    )
    tencent_hy_image_model: str = Field(
        default="hy-image-v3.5-preview",
        validation_alias=AliasChoices("TENCENT_HY_IMAGE_MODEL", "tencent_hy_image_model"),
    )
    tencent_hy_image_endpoint: str = Field(
        default="/v1/wand/hunyuan-image/v35-generation",
        validation_alias=AliasChoices(
            "TENCENT_HY_IMAGE_ENDPOINT", "tencent_hy_image_endpoint"
        ),
    )
    tokenhub_timeout_seconds: int = Field(
        default=180,
        ge=1,
        le=600,
        validation_alias=AliasChoices(
            "TENCENT_TOKENHUB_TIMEOUT_SECONDS", "tokenhub_timeout_seconds"
        ),
    )
    # 图片上传上限允许通过环境变量下调，但不能超过参考图业务上限。
    image_upload_max_bytes: int = Field(
        default=MAX_REFERENCE_IMAGE_BYTES,
        ge=1_024,
        le=MAX_REFERENCE_IMAGE_BYTES,
        validation_alias=AliasChoices("IMAGE_UPLOAD_MAX_BYTES", "image_upload_max_bytes"),
    )
    image_result_max_bytes: int = Field(
        default=52_428_800,
        ge=1_024,
        le=104_857_600,
        validation_alias=AliasChoices("IMAGE_RESULT_MAX_BYTES", "image_result_max_bytes"),
    )

    # 阿里云 OSS 仅保存用户上传的参考图和智能体生成的图片；Bucket 应保持私有。
    aliyun_oss_access_key_id: SecretStr = SecretStr("")
    aliyun_oss_access_key_secret: SecretStr = SecretStr("")
    aliyun_oss_endpoint: str = "https://oss-cn-hangzhou.aliyuncs.com"
    aliyun_oss_bucket: str = ""
    aliyun_oss_object_prefix: str = "nexusai"

    @property
    def aliyun_oss_configured(self) -> bool:
        """判断 OSS 所需密钥和 Bucket 是否齐全；未配置时不影响非图片智能体启动。"""
        return all(
            (
                self.aliyun_oss_access_key_id.get_secret_value().strip(),
                self.aliyun_oss_access_key_secret.get_secret_value().strip(),
                self.aliyun_oss_endpoint.strip(),
                self.aliyun_oss_bucket.strip(),
            )
        )

    volcengine_ark_api_key: SecretStr = SecretStr("")
    volcengine_ark_base_url: str = "https://ark.cn-beijing.volces.com/api/v3"
    volcengine_seedream_model: str = "doubao-seedream-5-0-flash-260915"

    database_url: str | None = None

    agent_max_steps: int = Field(default=20, ge=2, le=100)
    agent_max_tool_calls: int = Field(default=20, ge=1, le=100)
    agent_max_output_chars: int = Field(default=100_000, ge=1_000, le=1_000_000)
    agent_run_timeout_seconds: int = Field(default=180, ge=1, le=3600)
    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=60)
