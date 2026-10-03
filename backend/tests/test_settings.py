"""集中配置的默认模式与启用条件测试。"""

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from infra.settings import AppSettings


def test_settings_no_longer_expose_checkpoint_backend_switch() -> None:
    """持久化后端固定为 PostgreSQL，不再暴露 memory/postgres 选择项。"""
    settings = AppSettings(_env_file=None)

    assert not hasattr(settings, "checkpoint_backend")
    assert settings.database_url is None


def test_application_startup_requires_database_url() -> None:
    """应用始终使用 PostgreSQL，启动时缺少 DATABASE_URL 会明确失败。"""
    with pytest.raises(ValueError, match="DATABASE_URL"):
        with TestClient(create_app(AppSettings(_env_file=None))):
            pass

