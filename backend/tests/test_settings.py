"""集中配置的默认模式与启用条件测试。"""

import pytest
from pydantic import ValidationError

from infra.settings import AppSettings


def test_default_settings_do_not_require_database_configuration() -> None:
    """默认内存模式无需数据库连接即可加载。"""
    settings = AppSettings(_env_file=None)

    assert settings.checkpoint_backend == "memory"


def test_enabling_postgres_requires_database_url() -> None:
    """显式选择 PostgreSQL 时必须提供连接地址。"""
    with pytest.raises(ValidationError):
        AppSettings(checkpoint_backend="postgres", database_url=None, _env_file=None)

