"""检查本轮用户消息，通过校验后继续执行图。"""

from collections.abc import Awaitable, Callable

from langchain_core.messages import HumanMessage

from agents.job_agent.config import JobAgentConfig
from agents.job_agent.errors import JobAgentInputError
from agents.job_agent.state import JobAgentState


def create_input_node(
    config: JobAgentConfig,
) -> Callable[[JobAgentState], Awaitable[dict[str, str]]]:
    """创建输入校验节点；校验通过后流向 agent_node，不写入额外状态。"""

    async def input_node(state: JobAgentState) -> dict[str, str]:
        messages = state.get("messages", [])
        latest_user_message = next(
            (message for message in reversed(messages) if isinstance(message, HumanMessage)),
            None,
        )
        if latest_user_message is None or not isinstance(latest_user_message.content, str):
            raise JobAgentInputError(
                "本轮需要提供文本格式的用户消息",
                code="invalid_user_message",
            )

        request_text = latest_user_message.content.strip()
        if not request_text:
            raise JobAgentInputError("用户消息不能为空", code="empty_user_message")
        if len(request_text) > config.max_input_chars:
            raise JobAgentInputError(
                "用户消息超过允许的长度",
                code="input_too_long",
            )

        return {}

    return input_node
