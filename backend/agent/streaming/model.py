"""生成模型完整消息，同时让 LangGraph 观察到底层流式消息块。"""

from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, message_chunk_to_message
from langchain_core.runnables import RunnableConfig


async def invoke_chat_model_streaming(
    model: Any,
    messages: Sequence[BaseMessage],
    config: RunnableConfig | None = None,
) -> AIMessage:
    """优先流式调用模型，并累积 chunk 供后续图路由和消息持久化使用。"""
    stream = getattr(model, "astream", None)
    if not callable(stream):
        # 兼容仅实现 ainvoke 的轻量测试模型和自定义 Provider。
        response = await model.ainvoke(list(messages))
        if not isinstance(response, AIMessage):
            raise TypeError("聊天模型必须返回 AIMessage")
        return response

    full_response: AIMessageChunk | None = None
    async for chunk in stream(list(messages), config=config):
        if not isinstance(chunk, AIMessageChunk):
            continue
        full_response = chunk if full_response is None else full_response + chunk

    if full_response is None:
        return AIMessage(content="")

    response = message_chunk_to_message(full_response)
    if not isinstance(response, AIMessage):
        raise TypeError("流式聊天模型必须产生 AIMessageChunk")
    return response
