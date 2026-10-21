"""从最后一条模型回复中提取稳定的用户可见文本。"""

from collections.abc import Mapping

from langchain_core.messages import AIMessage

from agents.job_agent.errors import JobAgentExecutionError
from agents.job_agent.state import JobAgentState


def _extract_text(content: object) -> str:
    """提取纯文本或多模态消息中的文本块，不转述非文本载荷。"""

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        text_parts = [
            block["text"]
            for block in content
            if isinstance(block, Mapping)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        return "\n".join(part.strip() for part in text_parts if part.strip())
    return ""


async def output_node(state: JobAgentState) -> dict[str, str]:
    """读取最后一条 AI 消息并输出 answer 字段，供图转到 END。"""

    last_ai_message = next(
        (
            message
            for message in reversed(state.get("messages", []))
            if isinstance(message, AIMessage)
        ),
        None,
    )
    if last_ai_message is None or last_ai_message.tool_calls:
        raise JobAgentExecutionError(
            "当前图状态中没有可作为最终回答的模型消息",
            code="missing_final_message",
        )

    answer = _extract_text(last_ai_message.content)
    if not answer:
        raise JobAgentExecutionError(
            "模型没有生成可展示的文本回答",
            code="empty_final_answer",
        )
    return {"answer": answer}
