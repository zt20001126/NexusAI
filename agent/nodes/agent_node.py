"""业务决策节点。"""

import uuid

from langchain_core.messages import AIMessage

from agent.state import AgentState


async def agent_node(state: AgentState) -> dict[str, list[AIMessage]]:
    """根据信息完整度选择追问或示例业务工具。"""
    goal = state.get("resume_answers", {}).get("goal")
    if isinstance(goal, str) and goal.strip():
        tool_name = "summarize_goal"
        args = {"goal": goal}
    else:
        tool_name = "ask_user_question"
        args = {}
    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[{
                    "name": tool_name,
                    "args": args,
                    "id": f"tool-{uuid.uuid4().hex}",
                    "type": "tool_call",
                }],
            )
        ]
    }
