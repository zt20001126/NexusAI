"""Listing 图中可序列化的运行上下文。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ListingAgentState(TypedDict, total=False):
    """分开保存用户输入、视觉观察、确认答案和生成结果。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    resume_answers: dict[str, Any]
    confirmed_answers: dict[str, Any]
    agent_id: str
    principal_id: str
    conversation_id: str
    run_id: str
    task_result_id: str
    question_round_count: int
    attachment_ids: list[str]
    image_analysis: dict[str, Any]
    product_facts: dict[str, Any]
    questions: list[dict[str, Any]]
    listing_result: dict[str, Any]
