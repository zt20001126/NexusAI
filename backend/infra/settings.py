"""集中管理应用、模型和基础设施配置。"""

from pydantic import AliasChoices, Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from agent.constants import MAX_REFERENCE_IMAGE_BYTES
from agents.research_agent.constants import (
    RESEARCH_DEFAULT_MAX_ROUNDS,
    RESEARCH_MAX_SEARCH_ROUNDS,
)
from agents.literature_reader_agent.constants import (
    LITERATURE_DEFAULT_CANDIDATE_COUNT,
    LITERATURE_DEFAULT_TOP_K,
)


class AppSettings(BaseSettings):
    """应用配置。

    统一管理模型、数据库和智能体运行限制。应用运行时始终使用 PostgreSQL，
    DATABASE_URL 是唯一的应用数据库连接配置；本地运行时指向 localhost，
    Compose 网络内由服务配置覆盖为 postgres 主机名。健康巡检配置控制 PostgreSQL 和 Redis
    Broker 的后台探测频率与单项超时；过短的巡检间隔会增加基础设施连接开销。内存适配器只供测试代码显式使用。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    app_env: str = "development"
    # Snowflake worker ID 在同一套部署中的并发进程间必须唯一；1023 保留给历史迁移。
    snowflake_worker_id: int = Field(default=0, ge=0, le=1022)
    deepseek_api_key: SecretStr = SecretStr("")
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: int = Field(default=60, ge=1, le=600)

    # 劳动法律 RAG 使用 TokenHub OpenAI 兼容 Embedding 服务；向量维度须与数据库迁移一致。
    legal_embedding_base_url: str = "https://tokenhub.tencentmaas.com/v1"
    legal_embedding_model: str = "kinfra-text-embedding-0.6b"
    legal_embedding_timeout_seconds: int = Field(default=60, ge=1, le=600)
    legal_embedding_max_retries: int = Field(default=2, ge=0, le=5)
    legal_rag_top_k: int = Field(default=8, ge=1, le=30)
    legal_rag_candidate_count: int = Field(default=30, ge=5, le=100)
    legal_rag_min_similarity: float = Field(default=0.32, ge=0, le=1)
    legal_rag_max_context_chars: int = Field(default=24_000, ge=2_000, le=100_000)

    tencent_cloud_secret_id: SecretStr = SecretStr("")
    tencent_cloud_secret_key: SecretStr = SecretStr("")
    tencent_hunyuan_image_region: str = "ap-guangzhou"
    tencent_hunyuan_image_endpoint: str = "https://aiart.tencentcloudapi.com"
    tencent_hunyuan_image_api_version: str = "2022-12-29"
    tencent_hunyuan_image_action: str = "TextToImageLite"

    # TokenHub API Key 供图片智能体和劳动法律 Embedding 共用；受限 Key 需授权相应模型。
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

    # OpenAlex 免密可用；配置密钥后通过 Bearer Header 提高服务端额度。
    openalex_api_key: SecretStr = Field(
        default=SecretStr(""),
        validation_alias=AliasChoices("OPENALEX_API_KEY", "openalex_api_key"),
    )
    openalex_timeout_seconds: int = Field(
        default=20,
        ge=1,
        le=120,
        validation_alias=AliasChoices(
            "OPENALEX_TIMEOUT_SECONDS", "openalex_timeout_seconds"
        ),
    )
    openalex_max_retries: int = Field(
        default=2,
        ge=0,
        le=5,
        validation_alias=AliasChoices(
            "OPENALEX_MAX_RETRIES", "openalex_max_retries"
        ),
    )
    openalex_retry_delay_seconds: float = Field(
        default=0.5,
        ge=0,
        le=5,
        validation_alias=AliasChoices(
            "OPENALEX_RETRY_DELAY_SECONDS", "openalex_retry_delay_seconds"
        ),
    )
    research_max_search_rounds: int = Field(
        default=RESEARCH_DEFAULT_MAX_ROUNDS,
        ge=1,
        le=RESEARCH_MAX_SEARCH_ROUNDS,
        validation_alias=AliasChoices(
            "RESEARCH_MAX_SEARCH_ROUNDS", "research_max_search_rounds"
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

    # 文献 Worker 使用 Redis Broker；Celery 不使用结果后端，处理状态以 PostgreSQL 为准。
    celery_broker_url: str = Field(
        default="redis://127.0.0.1:6379/1",
        validation_alias=AliasChoices("CELERY_BROKER_URL", "celery_broker_url"),
    )
    # Agent 事件流沿用 Redis Broker 服务，但使用独立 key 前缀和有界保留策略。
    agent_event_max_length: int = Field(default=2_000, ge=100, le=100_000)
    agent_event_ttl_seconds: int = Field(default=86_400, ge=300, le=604_800)
    agent_event_redis_timeout_seconds: int = Field(default=5, ge=1, le=30)
    agent_worker_snowflake_id: int = Field(
        default=2,
        ge=0,
        le=1_020,
        validation_alias=AliasChoices("AGENT_WORKER_SNOWFLAKE_ID", "agent_worker_snowflake_id"),
    )
    # Celery Worker 使用独立 Snowflake worker ID；并行 Worker 部署时各进程必须唯一。
    literature_worker_snowflake_id: int = Field(
        default=1,
        ge=0,
        le=1_021,
        validation_alias=AliasChoices(
            "LITERATURE_WORKER_SNOWFLAKE_ID", "literature_worker_snowflake_id"
        ),
    )
    # PDF 文献入库资源上限与检索边界；Compose 使用 CELERY_BROKER_URL 指向 Redis 服务。
    literature_upload_max_bytes: int = Field(
        default=31_457_280,
        ge=1_024,
        le=104_857_600,
        validation_alias=AliasChoices(
            "LITERATURE_UPLOAD_MAX_BYTES", "literature_upload_max_bytes"
        ),
    )
    literature_max_pages: int = Field(
        default=400,
        ge=1,
        le=2_000,
        validation_alias=AliasChoices("LITERATURE_MAX_PAGES", "literature_max_pages"),
    )
    literature_chunk_max_chars: int = Field(
        default=1_200,
        ge=200,
        le=8_000,
        validation_alias=AliasChoices(
            "LITERATURE_CHUNK_MAX_CHARS", "literature_chunk_max_chars"
        ),
    )
    literature_context_max_chars: int = Field(
        default=24_000,
        ge=2_000,
        le=100_000,
        validation_alias=AliasChoices(
            "LITERATURE_CONTEXT_MAX_CHARS", "literature_context_max_chars"
        ),
    )
    literature_top_k: int = Field(
        default=LITERATURE_DEFAULT_TOP_K,
        ge=1,
        le=30,
        validation_alias=AliasChoices("LITERATURE_TOP_K", "literature_top_k"),
    )
    literature_candidate_count: int = Field(
        default=LITERATURE_DEFAULT_CANDIDATE_COUNT,
        ge=5,
        le=100,
        validation_alias=AliasChoices(
            "LITERATURE_CANDIDATE_COUNT", "literature_candidate_count"
        ),
    )
    literature_min_similarity: float = Field(
        default=0.32,
        ge=0,
        le=1,
        validation_alias=AliasChoices(
            "LITERATURE_MIN_SIMILARITY", "literature_min_similarity"
        ),
    )
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
    conversation_title_timeout_seconds: int = Field(default=8, ge=1, le=60)
    sse_heartbeat_seconds: int = Field(default=15, ge=5, le=60)

    # 后端依赖健康巡检配置，控制 Postgres/Redis 探测频率和单次超时；间隔过短会增加基础设施连接开销。
    health_check_interval_seconds: int = Field(default=30, ge=5, le=300)
    health_check_timeout_seconds: int = Field(default=3, ge=1, le=30)
