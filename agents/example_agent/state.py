"""示例智能体可持久化图状态。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ExampleAgentState(TypedDict, total=False):
    """保存对话、原始请求和恢复答案，不保存客户端或密钥对象。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    resume_answers: dict[str, Any]

