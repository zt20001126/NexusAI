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


def test_image_provider_environment_variables_match_environment_template(monkeypatch) -> None:
    """图片超时和文件大小配置使用 .env.example 中声明的环境变量名。"""
    monkeypatch.setenv("TENCENT_TOKENHUB_TIMEOUT_SECONDS", "37")
    monkeypatch.setenv("IMAGE_UPLOAD_MAX_BYTES", "1048576")
    monkeypatch.setenv("IMAGE_RESULT_MAX_BYTES", "2097152")

    settings = AppSettings(_env_file=None)

    assert settings.tokenhub_timeout_seconds == 37
    assert settings.image_upload_max_bytes == 1_048_576
    assert settings.image_result_max_bytes == 2_097_152


def test_conversation_title_timeout_is_configurable(monkeypatch) -> None:
    """标题生成时限由环境变量配置，控制首轮命名的最长等待时间。"""
    monkeypatch.setenv("CONVERSATION_TITLE_TIMEOUT_SECONDS", "12")

    settings = AppSettings(_env_file=None)

    assert settings.conversation_title_timeout_seconds == 12

