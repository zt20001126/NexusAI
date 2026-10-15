"""会话标题生成与模型输出规范化测试。"""

from typing import Any

import pytest

from agent.title import (
    MAX_CONVERSATION_TITLE_LENGTH,
    ModelConversationTitleGenerator,
    fallback_conversation_title,
    normalize_conversation_title,
)


class _FakeResponse:
    """保存模型返回内容的最小响应对象。"""

    def __init__(self, content: Any) -> None:
        self.content = content


class _FakeModel:
    """记录标题调用消息并返回固定内容。"""

    def __init__(self, response: _FakeResponse | Exception) -> None:
        self.response = response
        self.messages: list[Any] = []

    async def ainvoke(self, messages: list[Any]) -> _FakeResponse:
        self.messages = messages
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


class _FakeProvider:
    """向标题生成器注入无需网络的模型。"""

    def __init__(self, model: _FakeModel) -> None:
        self.model = model

    def create_chat_model(self) -> _FakeModel:
        return self.model


@pytest.mark.asyncio
async def test_title_generator_uses_first_message_and_cleans_model_output() -> None:
    """生成器只把首条用户消息交给模型，并清理标题格式。"""
    model = _FakeModel(_FakeResponse('“订单查询需求”\n额外解释'))
    generator = ModelConversationTitleGenerator(_FakeProvider(model), timeout_seconds=1)

    title = await generator.generate_title("帮我设计一个订单查询助手")

    assert title == "订单查询需求"
    assert model.messages[1].content == "帮我设计一个订单查询助手"


def test_title_normalization_limits_length_and_uses_first_nonempty_line() -> None:
    """模型输出仅保留首行，且标题长度受业务上限约束。"""
    title = normalize_conversation_title(f"\n标题：{'会话' * 40}\n其他内容")

    assert title is not None
    assert title == ("会话" * 25)[:MAX_CONVERSATION_TITLE_LENGTH]
    assert len(title) <= MAX_CONVERSATION_TITLE_LENGTH
    assert normalize_conversation_title([{"text": "标题：‘新标题’"}, {"text": 42}]) == "新标题"


@pytest.mark.asyncio
async def test_title_generator_returns_none_when_model_fails() -> None:
    """模型错误转换为空结果，交由运行器使用回退标题。"""
    generator = ModelConversationTitleGenerator(
        _FakeProvider(_FakeModel(RuntimeError("provider unavailable"))),
        timeout_seconds=1,
    )

    assert await generator.generate_title("帮我规划需求") is None


def test_fallback_title_preserves_existing_first_message_behavior() -> None:
    """模型不可用时压缩空白并截取首条消息，空内容使用默认名称。"""
    assert fallback_conversation_title("  帮我\n整理   业务  ") == "帮我 整理 业务"
    assert fallback_conversation_title(" \n ") == "新会话"
