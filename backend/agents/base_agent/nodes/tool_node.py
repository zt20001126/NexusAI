"""统一创建工具执行节点，并将工具异常转为受控模型观察结果。"""

import logging

from langgraph.prebuilt import ToolNode

from agents.base_agent.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)
TOOL_FAILURE_FEEDBACK = "工具执行失败。请勿编造工具结果；可调整调用后重试，或向用户说明无法完成。"


def _handle_tool_error(error: Exception) -> str:
    """记录不含异常详情的失败类型，并返回统一的工具错误观察。"""

    logger.warning("智能体工具执行失败 error_type=%s", type(error).__name__)
    return TOOL_FAILURE_FEEDBACK


def create_tool_node(tool_registry: ToolRegistry) -> ToolNode:
    """输入 AI 工具调用并追加 ToolMessage；执行后由图返回 chat_node。

    空工具集仍可构建，但没有已注册工具调用时图不会进入此节点。
    """

    return ToolNode(
        list(tool_registry.tools),
        name="tool_node",
        handle_tool_errors=_handle_tool_error,
    )
