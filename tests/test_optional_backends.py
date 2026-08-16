"""外部基础设施与模型适配器的预留边界测试。"""

import pytest

from agent_core.errors import BackendNotConfiguredError, ModelNotConfiguredError
from agent_core.models.provider import OpenAICompatibleProvider
from agent_core.runtime.factory import build_runtime
from infra.settings import AppSettings


def test_external_backend_configuration_does_not_connect_implicitly() -> None:
    """启用预留后端时明确报告尚未实现，不尝试建立真实网络连接。"""
    settings = AppSettings(
        checkpoint_backend="postgres",
        database_url="postgresql://placeholder/agent",
        lock_backend="redis",
        event_bus_backend="redis",
        redis_url="redis://placeholder:6379/0",
        task_backend="celery",
        celery_broker_url="redis://placeholder:6379/1",
        _env_file=None,
    )

    with pytest.raises(BackendNotConfiguredError) as error:
        build_runtime(settings)

    assert error.value.code == "BACKEND_NOT_CONFIGURED"


def test_model_provider_requires_configuration_only_when_created() -> None:
    """应用可在未配置模型时启动，真正创建模型时才返回稳定配置错误。"""
    provider = OpenAICompatibleProvider(AppSettings(_env_file=None))

    with pytest.raises(ModelNotConfiguredError) as error:
        provider.create_chat_model()

    assert error.value.code == "MODEL_NOT_CONFIGURED"

