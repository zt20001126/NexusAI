"""后端健康检查接口使用的状态枚举和响应 DTO。"""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class HealthStatus(StrEnum):
    """健康探针和整体就绪状态的稳定取值。"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class HealthProbeErrorCode(StrEnum):
    """健康探针向调用方暴露的安全错误码。"""

    CHECK_FAILED = "CHECK_FAILED"
    TIMEOUT = "TIMEOUT"


class HealthProbeResult(BaseModel):
    """单个基础设施探针的结果，不包含连接地址或底层异常文本。"""

    status: HealthStatus = Field(description="该依赖最近一次探测的健康状态")
    latency_ms: float = Field(ge=0, description="本次探测耗时，单位为毫秒")
    checked_at: datetime = Field(description="本次探测完成时间")
    error_code: HealthProbeErrorCode | None = Field(
        default=None,
        description="探测失败时返回的稳定错误码",
    )


class HealthCheckResponse(BaseModel):
    """就绪检查响应，包含缓存的依赖状态及其新鲜度。"""

    status: HealthStatus = Field(description="后端当前是否具备处理业务请求的条件")
    checked_at: datetime | None = Field(
        default=None,
        description="最近一轮依赖巡检完成时间",
    )
    stale: bool = Field(description="最近一轮巡检是否已超过允许的新鲜度")
    checks: dict[str, HealthProbeResult] = Field(
        default_factory=dict,
        description="按依赖名称索引的探测结果",
    )


class HealthLivenessResponse(BaseModel):
    """存活检查响应，只表明 HTTP 进程当前能够处理请求。"""

    status: HealthStatus = Field(
        default=HealthStatus.HEALTHY,
        description="HTTP 进程的存活状态",
    )
