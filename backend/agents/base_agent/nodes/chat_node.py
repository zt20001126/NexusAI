"""根据系统提示词和对话状态调用模型，并允许模型选择已注册工具。"""

import logging
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from agent.streaming.model import invoke_chat_model_streaming
from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.errors import BaseAgentExecutionError
from agents.base_agent.state import BaseAgentState
from agents.base_agent.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


def create_chat_node(
    *,
    config: BaseAgentConfig,
    chat_model: BaseChatModel,
    tool_registry: ToolRegistry,
) -> Callable[..., Any]:
    """输入对话状态并追加 AI 消息；后续由图路由到 tool_node 或 answer_node。"""

    model = (
        chat_model.bind_tools(list(tool_registry.tools))
        if tool_registry.tools
        else chat_model
    )

    async def chat_node(
        state: BaseAgentState,
        runnable_config: RunnableConfig | None = None,
    ) -> dict[str, list[BaseMessage]]:
        # 每轮使用当前配置中的系统提示词，避免 Checkpoint 中遗留旧提示词。
        conversation = [
            message
            for message in state.get("messages", [])
            if not isinstance(message, SystemMessage)
        ]
        prompt = [SystemMessage(content=config.system_prompt), *conversation]

        try:
            # 经共享流式模型适配器调用，RunnableConfig 会让 LangGraph 收到模型增量片段。
            response = await invoke_chat_model_streaming(
                model,
                prompt,
                runnable_config,
            )
        except Exception as error:
            logger.warning(
                "智能体模型调用失败 agent_id=%s error_type=%s",
                config.agent_id,
                type(error).__name__,
            )
            raise BaseAgentExecutionError(
                "模型调用失败",
                code="model_call_failed",
            ) from None

        if not isinstance(response, AIMessage):
            raise BaseAgentExecutionError(
                "模型返回了不支持的消息类型",
                code="invalid_model_response",
            )
        return {"messages": [response]}

    return chat_node
