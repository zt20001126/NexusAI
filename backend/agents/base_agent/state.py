"""LangGraph 状态定义；仅保存可序列化的对话业务数据。"""

from typing import Annotated, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class BaseAgentState(TypedDict, total=False):
    """在节点间传递的对话消息和最终回答。"""

    messages: Annotated[list[BaseMessage], add_messages]
    answer: str
