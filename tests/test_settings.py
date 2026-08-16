"""集中配置的默认模式与启用条件测试。"""

import pytest
from pydantic import ValidationError

from infra.settings import AppSettings


def test_default_settings_do_not_require_external_infrastructure() -> None:
    """默认内存模式无需数据库、Redis 或 Celery 地址即可加载。"""
    settings = AppSettings(_env_file=None)

    assert settings.checkpoint_backend == "memory"
    assert settings.lock_backend == "memory"
    assert settings.event_bus_backend == "memory"
    assert settings.task_backend == "disabled"


def test_enabling_redis_requires_redis_url() -> None:
    """显式启用 Redis 后必须提供地址，避免运行到一半才出现隐式故障。"""
    with pytest.raises(ValidationError):
        AppSettings(lock_backend="redis", redis_url=None, _env_file=None)

