"""示例智能体节点与图构建。"""

import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from agent_core.graph.react import build_react_graph
from agents.example_agent.state import ExampleAgentState
from agents.example_agent.tools import EXAMPLE_TOOLS


async def example_agent_node(state: ExampleAgentState) -> dict[str, list[AIMessage]]:
    """根据当前状态发起追问、调用目标整理工具或生成最终回复。"""
    messages = state.get("messages", [])
    last_message = messages[-1] if messages else None
    if isinstance(last_message, ToolMessage) and last_message.name == "summarize_goal":
        try:
            payload = json.loads(str(last_message.content))
            summary = str(payload["data"]["summary"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            summary = "目标已经整理完成。"
        return {
            "messages": [
                AIMessage(content=f"{summary}。你现在可以继续添加业务节点和工具。")
            ]
        }

    answers = state.get("resume_answers", {})
    goal = answers.get("goal")
    if isinstance(goal, str) and goal.strip():
        return {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "summarize_goal",
                            "args": {"goal": goal},
                            "id": f"tool-{uuid.uuid4().hex}",
                            "type": "tool_call",
                        }
                    ],
                )
            ]
        }

    return {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "ask_user_question",
                        "args": {},
                        "id": f"tool-{uuid.uuid4().hex}",
                        "type": "tool_call",
                    }
                ],
            )
        ]
    }


def create_example_graph(checkpointer: Any) -> Any:
    """使用通用构建器创建可恢复的示例智能体图。"""
    return build_react_graph(
        state_schema=ExampleAgentState,
        agent_node=example_agent_node,
        tools=EXAMPLE_TOOLS,
        checkpointer=checkpointer,
        pause_tool_names=frozenset({"ask_user_question"}),
    )
