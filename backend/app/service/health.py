"""编排基础设施健康探针并维护最近一次就绪状态。"""

import asyncio
import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from time import perf_counter
from typing import Protocol

from app.schemas.health import (
    HealthCheckResponse,
    HealthProbeErrorCode,
    HealthProbeResult,
    HealthStatus,
)

logger = logging.getLogger(__name__)
# 三个巡检周期内没有新结果时，将就绪状态视为过期。
HEALTH_STALE_INTERVAL_MULTIPLIER = 3


class HealthProbe(Protocol):
    """可由健康巡检器调用的单项基础设施探针接口。"""

    name: str

    async def check(self) -> None:
        """依赖可用时正常返回，不可用时抛出异常。"""
        ...


class HealthMonitor:
    """执行定时依赖巡检，并向 HTTP 层提供脱敏的最近状态。"""

    def __init__(
        self,
        probes: Sequence[HealthProbe],
        *,
        interval_seconds: float,
        timeout_seconds: float,
    ) -> None:
        """注入基础设施探针与巡检时限，避免在服务模块中创建外部客户端。"""
        if not probes:
            raise ValueError("至少需要配置一个健康探针")
        if interval_seconds <= 0 or timeout_seconds <= 0:
            raise ValueError("健康巡检间隔和超时必须大于零")

        probe_names = [probe.name for probe in probes]
        if len(probe_names) != len(set(probe_names)):
            raise ValueError("健康探针名称不能重复")

        self._probes = tuple(probes)
        self._interval_seconds = interval_seconds
        self._timeout_seconds = timeout_seconds
        self._stale_after_seconds = (
            interval_seconds * HEALTH_STALE_INTERVAL_MULTIPLIER
        )
        self._last_report: HealthCheckResponse | None = None
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        """启动巡检。

        Step 1: 立即执行一轮探测，使就绪接口启动后即可返回真实状态。
        Step 2: 创建后台任务，按配置间隔继续刷新状态快照。
        """
        if self._task is not None and not self._task.done():
            return

        await self.check_once()
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(
            self._run_periodically(),
            name="backend-health-monitor",
        )

    async def stop(self) -> None:
        """通知后台巡检任务退出并等待当前探测结束。"""
        if self._task is None or self._stop_event is None:
            return

        self._stop_event.set()
        await self._task
        self._task = None
        self._stop_event = None

    async def check_once(self) -> HealthCheckResponse:
        """并发执行一轮探测，将每个依赖的结果收敛为单份状态快照。

        Step 1: 并发调用所有依赖探针，避免单项探测依次累积等待时间。
        Step 2: 根据全部探针结果计算总体状态并生成时间戳快照。
        Step 3: 更新最近一次结果，供就绪接口读取。
        """
        results = await asyncio.gather(
            *(self._check_probe(probe) for probe in self._probes)
        )
        checks = {name: result for name, result in results}
        status = (
            HealthStatus.HEALTHY
            if all(result.status == HealthStatus.HEALTHY for result in checks.values())
            else HealthStatus.UNHEALTHY
        )
        report = HealthCheckResponse(
            status=status,
            checked_at=datetime.now(UTC),
            stale=False,
            checks=checks,
        )
        self._last_report = report
        return report

    def snapshot(self) -> HealthCheckResponse:
        """读取最近一次探测结果，并将过期状态视为未就绪。"""
        if self._last_report is None or self._last_report.checked_at is None:
            return HealthCheckResponse(
                status=HealthStatus.UNHEALTHY,
                stale=True,
            )

        is_stale = (
            datetime.now(UTC) - self._last_report.checked_at
        ).total_seconds() > self._stale_after_seconds
        status = (
            HealthStatus.UNHEALTHY
            if is_stale
            else self._last_report.status
        )
        return self._last_report.model_copy(
            update={"status": status, "stale": is_stale}
        )

    async def _run_periodically(self) -> None:
        """按间隔刷新健康快照；单轮意外错误不会终止后续巡检。"""
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self._interval_seconds,
                )
            except TimeoutError:
                try:
                    await self.check_once()
                except Exception:
                    logger.exception("health_check_cycle_failed")

    async def _check_probe(
        self,
        probe: HealthProbe,
    ) -> tuple[str, HealthProbeResult]:
        """执行单个探针、记录耗时并将异常转换为安全错误码。"""
        started_at = perf_counter()
        try:
            await asyncio.wait_for(
                probe.check(),
                timeout=self._timeout_seconds,
            )
        except TimeoutError:
            status = HealthStatus.UNHEALTHY
            error_code = HealthProbeErrorCode.TIMEOUT
            logger.warning("health_probe_failed probe=%s error=timeout", probe.name)
        except Exception as error:
            status = HealthStatus.UNHEALTHY
            error_code = HealthProbeErrorCode.CHECK_FAILED
            logger.warning(
                "health_probe_failed probe=%s error_type=%s",
                probe.name,
                type(error).__name__,
            )
        else:
            status = HealthStatus.HEALTHY
            error_code = None

        result = HealthProbeResult(
            status=status,
            latency_ms=(perf_counter() - started_at) * 1_000,
            checked_at=datetime.now(UTC),
            error_code=error_code,
        )
        return probe.name, result
