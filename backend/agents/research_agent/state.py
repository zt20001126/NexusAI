"""LangGraph 检索运行中保留的轻量状态。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agent.enums import AgentType

class ResearchAgentState(TypedDict, total=False):
    """保留查询计划和任务上下文，不把论文数组写入 Checkpoint。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    research_options: dict[str, Any]
    search_plan: dict[str, Any]
    agent: AgentType
    principal_id: str
    conversation_id: str
    run_id: str
    task_result_id: str
