"""检查本轮用户消息，并向后续节点提供规范化请求。"""

from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage

from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.errors import BaseAgentInputError
from agents.base_agent.state import BaseAgentState


def create_validation_node(
    config: BaseAgentConfig,
) -> Callable[[BaseAgentState], Awaitable[dict[str, str]]]:
    """创建输入校验节点；输入为图状态，输出规范化请求文本并流向 chat_node。"""

    async def validation_node(state: BaseAgentState) -> dict[str, str]:
        messages = state.get("messages", [])
        latest_user_message = next(
            (message for message in reversed(messages) if isinstance(message, HumanMessage)),
            None,
        )
        if latest_user_message is None or not isinstance(latest_user_message.content, str):
            raise BaseAgentInputError(
                "本轮需要提供文本格式的用户消息",
                code="invalid_user_message",
            )

        request_text = latest_user_message.content.strip()
        if not request_text:
            raise BaseAgentInputError("用户消息不能为空", code="empty_user_message")
        if len(request_text) > config.max_input_chars:
            raise BaseAgentInputError(
                "用户消息超过允许的长度",
                code="input_too_long",
            )

        return {"original_request": request_text}

    return validation_node
