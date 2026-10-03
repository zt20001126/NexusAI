"""外部基础设施与模型适配器的预留边界测试。"""

import pytest

from agent.errors import ModelNotConfiguredError
from agent.runner import AgentRunner, build_memory_runner
from infra.model_provider import OpenAICompatibleProvider
from infra.settings import AppSettings


def test_memory_runner_remains_an_explicit_test_fixture() -> None:
    """内存运行器仅由测试显式构造，不再通过应用配置切换。"""
    runner = build_memory_runner(AppSettings(_env_file=None), graph=object())

    assert isinstance(runner, AgentRunner)


def test_model_provider_requires_configuration_only_when_created() -> None:
    """应用可在未配置模型时启动，真正创建模型时才返回稳定配置错误。"""
    provider = OpenAICompatibleProvider(AppSettings(_env_file=None))

    with pytest.raises(ModelNotConfiguredError) as error:
        provider.create_chat_model()

    assert error.value.code == "MODEL_NOT_CONFIGURED"
