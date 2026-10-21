"""集中配置的默认模式与启用条件测试。"""

import pytest
from fastapi.testclient import TestClient

from bootstrap.application import create_app
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


def test_health_check_interval_and_timeout_are_configurable(monkeypatch) -> None:
    """后端健康巡检间隔和单项探针超时可由部署环境覆盖。"""
    monkeypatch.setenv("HEALTH_CHECK_INTERVAL_SECONDS", "45")
    monkeypatch.setenv("HEALTH_CHECK_TIMEOUT_SECONDS", "5")

    settings = AppSettings(_env_file=None)

    assert settings.health_check_interval_seconds == 45
    assert settings.health_check_timeout_seconds == 5


def test_openalex_configuration_uses_environment_aliases(monkeypatch) -> None:
    """OpenAlex 凭据及重试配置可由部署环境覆盖。"""
    monkeypatch.setenv("OPENALEX_API_KEY", "test-key")
    monkeypatch.setenv("OPENALEX_TIMEOUT_SECONDS", "31")
    monkeypatch.setenv("OPENALEX_MAX_RETRIES", "4")
    monkeypatch.setenv("RESEARCH_MAX_SEARCH_ROUNDS", "2")

    settings = AppSettings(_env_file=None)

    assert settings.openalex_api_key.get_secret_value() == "test-key"
    assert settings.openalex_timeout_seconds == 31
    assert settings.openalex_max_retries == 4
    assert settings.research_max_search_rounds == 2


def test_shixiseng_configuration_uses_environment_aliases(monkeypatch) -> None:
    """实习僧商户凭证和 API 地址可从环境变量读取。"""
    monkeypatch.setenv("SHIXISENG_APP_ID", "test-app-id")
    monkeypatch.setenv("SHIXISENG_APP_SECRET", "test-app-secret")
    monkeypatch.setenv("SHIXISENG_BASE_URL", "https://example.test")
    settings = AppSettings(_env_file=None)

    assert settings.shixiseng_app_id.get_secret_value() == "test-app-id"
    assert settings.shixiseng_app_secret.get_secret_value() == "test-app-secret"
    assert settings.shixiseng_base_url == "https://example.test"


def test_shixiseng_configuration_has_safe_defaults() -> None:
    """未获批 API 凭证时保持空值，基础地址使用默认设置。"""
    settings = AppSettings(_env_file=None)

    assert settings.shixiseng_app_id.get_secret_value() == ""
    assert settings.shixiseng_app_secret.get_secret_value() == ""
    assert settings.shixiseng_base_url == "https://open.shixiseng.com"

