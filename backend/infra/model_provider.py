"""集中创建对话模型，避免节点直接读取环境变量。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_openai import ChatOpenAI

from agent.errors import ModelNotConfiguredError
from infra.settings import AppSettings


class ChatModelProvider(Protocol):
    """业务节点获取对话模型时依赖的公开协议。"""

    def create_chat_model(self) -> BaseChatModel: ...


class OpenAICompatibleProvider:
    """使用 DeepSeek 的 OpenAI-compatible API 创建对话模型。"""

    def __init__(self, settings: AppSettings) -> None:
        self._settings = settings

    def create_chat_model(self) -> ChatOpenAI:
        """按需创建模型；缺少配置时返回稳定业务异常。"""
        api_key = self._settings.deepseek_api_key.get_secret_value()
        if (
            not self._settings.deepseek_model
            or not api_key
            or api_key.startswith("replace_with_")
        ):
            raise ModelNotConfiguredError()
        return ChatOpenAI(
            model=self._settings.deepseek_model,
            api_key=api_key,
            base_url=self._settings.deepseek_base_url,
            timeout=self._settings.deepseek_timeout_seconds,
            max_retries=2,
        )


class StaticChatModelProvider:
    """供测试和离线示例使用的确定性模型 Provider。"""

    def __init__(self, responses: list[str]) -> None:
        if not responses:
            raise ValueError("至少需要一条固定模型响应")
        self._responses = list(responses)

    def create_chat_model(self) -> FakeListChatModel:
        """创建不产生网络请求的 LangChain Fake 模型。"""
        return FakeListChatModel(responses=list(self._responses))
