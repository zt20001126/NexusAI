"""后端进程存活和基础设施就绪检查接口。"""

from fastapi import APIRouter, Request, Response

from app.schemas.health import (
    HealthCheckResponse,
    HealthLivenessResponse,
    HealthStatus,
)
from app.service.health import HealthMonitor

router = APIRouter(tags=["健康检查"])


@router.get("/health/live", response_model=HealthLivenessResponse)
def check_liveness() -> HealthLivenessResponse:
    """返回进程存活状态，不依赖数据库或 Redis 的可用性。"""
    return HealthLivenessResponse(status=HealthStatus.HEALTHY)


@router.get(
    "/health/ready",
    response_model=HealthCheckResponse,
    responses={503: {"model": HealthCheckResponse, "description": "依赖未就绪"}},
)
def check_readiness(
    request: Request,
    response: Response,
) -> HealthCheckResponse:
    """返回最近一次依赖巡检结果，失败或过期时使用 HTTP 503。"""
    monitor: HealthMonitor = request.app.state.health_monitor
    report = monitor.snapshot()
    if report.status != HealthStatus.HEALTHY:
        response.status_code = 503
    return report
