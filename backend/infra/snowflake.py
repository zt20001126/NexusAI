"""业务主键生成器，供应用管理的业务表使用雪花 ID。"""

from __future__ import annotations

import threading
import time
from functools import lru_cache


SNOWFLAKE_EPOCH_MILLISECONDS = 1_704_067_200_000
MAX_WORKER_ID = 1_021
_WORKER_BITS = 10
_SEQUENCE_BITS = 12
_MAX_SEQUENCE = (1 << _SEQUENCE_BITS) - 1
_MAX_TIMESTAMP = (1 << 41) - 1


class SnowflakeIdGenerator:
    """线程安全地生成 PostgreSQL BIGINT 可保存的雪花 ID。"""

    def __init__(self, worker_id: int) -> None:
        """创建实例；集群中的每个并发应用进程必须配置唯一 worker_id。"""
        if worker_id < 0 or worker_id > MAX_WORKER_ID:
            raise ValueError(f"worker_id 必须在 0 到 {MAX_WORKER_ID} 之间")
        self._worker_id = worker_id
        self._lock = threading.Lock()
        self._last_timestamp = -1
        self._sequence = 0

    def next_id(self) -> int:
        """生成一个严格递增的雪花 ID；检测到系统时钟回拨时拒绝复用 ID。"""
        with self._lock:
            timestamp = self._current_timestamp()
            if timestamp < self._last_timestamp:
                raise RuntimeError("系统时钟发生回拨，暂时无法生成雪花 ID")
            if timestamp == self._last_timestamp:
                self._sequence = (self._sequence + 1) & _MAX_SEQUENCE
                if self._sequence == 0:
                    timestamp = self._wait_for_next_millisecond(self._last_timestamp)
            else:
                self._sequence = 0

            self._last_timestamp = timestamp
            elapsed = timestamp - SNOWFLAKE_EPOCH_MILLISECONDS
            if elapsed < 0 or elapsed > _MAX_TIMESTAMP:
                raise RuntimeError("系统时间超出雪花 ID 支持范围")
            return (
                (elapsed << (_WORKER_BITS + _SEQUENCE_BITS))
                | (self._worker_id << _SEQUENCE_BITS)
                | self._sequence
            )

    def next_id_string(self) -> str:
        """生成适合 API/SSE/JavaScript 传输的十进制字符串，避免精度损失。"""
        return str(self.next_id())

    @staticmethod
    def _current_timestamp() -> int:
        """读取当前 UTC 毫秒时间戳。"""
        return time.time_ns() // 1_000_000

    @classmethod
    def _wait_for_next_millisecond(cls, last_timestamp: int) -> int:
        """单毫秒内序号耗尽时等待下一个时间片。"""
        timestamp = cls._current_timestamp()
        while timestamp <= last_timestamp:
            time.sleep(0.0001)
            timestamp = cls._current_timestamp()
        return timestamp


@lru_cache(maxsize=32)
def get_snowflake_generator(worker_id: int = 0) -> SnowflakeIdGenerator:
    """复用同一 worker 的线程安全生成器，避免同进程内序号冲突。"""
    return SnowflakeIdGenerator(worker_id)


def to_database_id(value: str | int) -> int:
    """将 API 中的雪花十进制字符串转换为数据库 BIGINT 并校验范围。"""
    if isinstance(value, bool):
        raise ValueError("ID 必须是正整数")
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        raise ValueError("ID 必须是十进制雪花 ID") from None
    if resolved <= 0 or resolved > 9_223_372_036_854_775_807:
        raise ValueError("ID 超出 PostgreSQL BIGINT 范围")
    if str(resolved) != str(value):
        raise ValueError("ID 必须是不带前导符号或空格的十进制字符串")
    return resolved
