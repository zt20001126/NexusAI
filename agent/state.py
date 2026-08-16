"""唯一智能体的可持久化图状态。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class AgentState(TypedDict, total=False):
    """保存对话和受控业务字段，不保存客户端、连接或密钥对象。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    resume_answers: dict[str, Any]
