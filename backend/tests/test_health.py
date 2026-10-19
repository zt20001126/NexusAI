"""后端健康巡检服务和 HTTP 状态接口测试。"""

import asyncio

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.router.health import router as health_router
from app.schemas.health import HealthProbeErrorCode, HealthStatus
from app.service.health import HealthMonitor


class _FakeProbe:
    """通过可控异常模拟基础设施探针，不访问真实数据库或 Redis。"""

    def __init__(self, name: str, *, fail: bool = False) -> None:
        self.name = name
        self.fail = fail
        self.calls = 0

    async def check(self) -> None:
        self.calls += 1
        if self.fail:
            raise RuntimeError("sensitive connection detail")


class _PeriodicProbe:
    """记录后台任务调用次数，用于验证巡检周期和停止行为。"""

    name = "test"

    def __init__(self) -> None:
        self.calls = 0
        self.second_call = asyncio.Event()

    async def check(self) -> None:
        self.calls += 1
        if self.calls >= 2:
            self.second_call.set()


async def test_health_monitor_records_failures_and_recovers() -> None:
    """单项探针失败时保留其他结果，依赖恢复后整体状态随下一轮恢复。"""
    postgres_probe = _FakeProbe("postgres")
    redis_probe = _FakeProbe("redis", fail=True)
    monitor = HealthMonitor(
        [postgres_probe, redis_probe],
        interval_seconds=30,
        timeout_seconds=1,
    )

    failed_report = await monitor.check_once()

    assert failed_report.status == HealthStatus.UNHEALTHY
    assert failed_report.checks["postgres"].status == HealthStatus.HEALTHY
    assert failed_report.checks["redis"].status == HealthStatus.UNHEALTHY
    assert failed_report.checks["redis"].error_code == HealthProbeErrorCode.CHECK_FAILED
    assert "sensitive connection detail" not in failed_report.model_dump_json()

    redis_probe.fail = False
    recovered_report = await monitor.check_once()

    assert recovered_report.status == HealthStatus.HEALTHY
    assert redis_probe.calls == 2


async def test_health_monitor_times_out_a_slow_probe() -> None:
    """探针超过单项时限后以稳定 TIMEOUT 错误码报告失败。"""

    class _SlowProbe:
        name = "slow"

        async def check(self) -> None:
            await asyncio.sleep(1)

    monitor = HealthMonitor(
        [_SlowProbe()],
        interval_seconds=30,
        timeout_seconds=0.01,
    )

    report = await monitor.check_once()

    assert report.status == HealthStatus.UNHEALTHY
    assert report.checks["slow"].error_code == HealthProbeErrorCode.TIMEOUT


async def test_health_monitor_starts_immediately_and_stops_periodically() -> None:
    """后台任务启动时立即检查，按周期重试，并在停止后不再探测。"""
    probe = _PeriodicProbe()
    monitor = HealthMonitor(
        [probe],
        interval_seconds=0.01,
        timeout_seconds=0.1,
    )

    await monitor.start()
    assert probe.calls == 1
    await asyncio.wait_for(probe.second_call.wait(), timeout=1)
    await monitor.stop()
    stopped_calls = probe.calls
    await asyncio.sleep(0.03)

    assert probe.calls == stopped_calls


def test_health_routes_report_liveness_and_readiness() -> None:
    """存活接口独立于依赖状态，就绪接口按缓存状态返回 200 或 503。"""
    postgres_probe = _FakeProbe("postgres")
    redis_probe = _FakeProbe("redis")
    monitor = HealthMonitor(
        [postgres_probe, redis_probe],
        interval_seconds=30,
        timeout_seconds=1,
    )
    asyncio.run(monitor.check_once())
    app = FastAPI()
    app.include_router(health_router)
    app.state.health_monitor = monitor

    with TestClient(app) as client:
        live_response = client.get("/health/live")
        ready_response = client.get("/health/ready")

        assert live_response.status_code == 200
        assert live_response.json() == {"status": "healthy"}
        assert ready_response.status_code == 200
        assert ready_response.json()["status"] == "healthy"

        redis_probe.fail = True
        asyncio.run(monitor.check_once())
        failed_response = client.get("/health/ready")

        assert failed_response.status_code == 503
        assert failed_response.json()["status"] == "unhealthy"
        assert failed_response.json()["checks"]["redis"]["error_code"] == "CHECK_FAILED"
        assert "sensitive connection detail" not in failed_response.text
