"""集中创建对话模型，避免业务节点直接读取环境变量。"""

from typing import Protocol

from langchain_core.language_models import BaseChatModel
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_openai import ChatOpenAI

from agent_core.errors import ModelNotConfiguredError
from infra.settings import AppSettings


class ChatModelProvider(Protocol):
    """业务节点获取对话模型时依赖的公开协议。"""

    def create_chat_model(self) -> BaseChatModel:
        """创建或返回一个可调用的对话模型。"""
        ...


class OpenAICompatibleProvider:
    """创建 OpenAI 协议兼容的 LangChain 对话模型。"""

    def __init__(self, settings: AppSettings) -> None:
        """保存配置但不建立网络连接。"""
        self._settings = settings

    def create_chat_model(self) -> ChatOpenAI:
        """按需创建模型；缺少必要配置时返回稳定业务异常。"""
        api_key = self._settings.llm_api_key.get_secret_value()
        if not self._settings.llm_model or not api_key:
            raise ModelNotConfiguredError()
        return ChatOpenAI(
            model=self._settings.llm_model,
            api_key=api_key,
            base_url=self._settings.llm_base_url or None,
            timeout=self._settings.llm_timeout_seconds,
            max_retries=2,
        )


class StaticChatModelProvider:
    """供测试和离线示例使用的确定性模型 Provider。"""

    def __init__(self, responses: list[str]) -> None:
        """保存按调用顺序返回的固定响应。"""
        if not responses:
            raise ValueError("至少需要一条固定模型响应")
        self._responses = list(responses)

    def create_chat_model(self) -> FakeListChatModel:
        """创建 LangChain 标准 Fake 模型，不产生网络请求。"""
        return FakeListChatModel(responses=list(self._responses))
