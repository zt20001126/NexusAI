"""构建受控 Agent—Tool 循环。"""

from collections.abc import Callable, Sequence
from typing import Any

from langchain_core.messages import BaseMessage, ToolMessage
from langchain_core.tools import BaseTool
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.prebuilt import ToolNode


def build_react_graph(
    *,
    state_schema: type[Any],
    agent_node: Callable[..., Any],
    tools: Sequence[BaseTool],
    checkpointer: Any,
    pause_tool_names: frozenset[str] = frozenset(),
) -> Any:
    """构建标准 Agent—Tool 循环并绑定可替换 Checkpointer。

    工具注册表是允许调用名称的唯一来源；暂停工具完成后直接结束本次图
    执行，由运行时保存等待状态并在用户回答后重新进入图。
    """
    # ToolNode 在异常时只生成稳定安全文本，防止原始第三方异常进入 ToolMessage
    # 并在下一轮被模型读取。真实异常仍由工具自身在服务端记录。
    tool_node = ToolNode(list(tools), handle_tool_errors="工具执行失败，请稍后重试")
    graph = StateGraph(state_schema)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tool_node)
    graph.add_edge(START, "agent")

    def route_after_agent(state: dict[str, Any]) -> str:
        """模型产生工具调用时进入工具节点，否则结束本轮。"""
        messages: list[BaseMessage] = state.get("messages", [])
        if messages and getattr(messages[-1], "tool_calls", []):
            return "tools"
        return END

    def route_after_tools(state: dict[str, Any]) -> str:
        """追问工具结束当前轮次，普通工具回到 Agent 生成后续回复。"""
        messages: list[BaseMessage] = state.get("messages", [])
        last_message = messages[-1] if messages else None
        if isinstance(last_message, ToolMessage) and last_message.name in pause_tool_names:
            return END
        return "agent"

    graph.add_conditional_edges("agent", route_after_agent, ["tools", END])
    graph.add_conditional_edges("tools", route_after_tools, ["agent", END])
    compiled_graph = graph.compile(checkpointer=checkpointer)
    # 运行时注册阶段会比对该元数据与 AgentDefinition，防止业务开发者
    # 只更新图路由或只更新事件映射而造成无法恢复的半暂停状态。
    setattr(compiled_graph, "pause_tool_names", pause_tool_names)
    return compiled_graph
