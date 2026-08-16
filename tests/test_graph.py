"""单智能体节点、工具和图路由测试。"""

from langchain_core.messages import AIMessage, ToolMessage

from agent.graph import route_after_agent, route_after_tools
from agent.nodes.agent_node import agent_node
from agent.nodes.result_node import result_node
from agent.nodes.validation_node import validation_node


async def test_validation_node_normalizes_request() -> None:
    """输入节点去除首尾空白，后续业务节点无需重复处理。"""
    result = await validation_node({"original_request": "  创建订单助手  "})

    assert result == {"original_request": "创建订单助手"}


async def test_agent_node_asks_question_without_goal() -> None:
    """缺少目标时，决策节点只调用结构化追问工具。"""
    result = await agent_node({"resume_answers": {}})

    assert result["messages"][0].tool_calls[0]["name"] == "ask_user_question"


async def test_result_node_formats_safe_summary() -> None:
    """结果节点只从结构化工具载荷提取用户可见摘要。"""
    result = await result_node(
        {
            "messages": [
                ToolMessage(
                    content='{"success":true,"data":{"summary":"已确认目标：订单查询"}}',
                    tool_call_id="tool-1",
                    name="summarize_goal",
                )
            ]
        }
    )

    assert "订单查询" in result["messages"][0].content


def test_pause_tool_ends_current_graph_run() -> None:
    """追问工具结束当前图执行，由运行器保存 WAITING 状态等待恢复。"""
    route = route_after_tools(
        {
            "messages": [
                ToolMessage(content="{}", tool_call_id="tool-1", name="ask_user_question")
            ]
        }
    )

    assert route == "__end__"


def test_direct_agent_answer_does_not_enter_tool_node() -> None:
    """未来模型直接回答且没有工具调用时，不应错误进入 ToolNode。"""
    assert route_after_agent({"messages": [AIMessage(content="直接回答")]}) == "__end__"
