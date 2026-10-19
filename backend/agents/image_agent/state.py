"""淘宝图片生成图在运行期间保存的有界、可序列化状态。"""

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages

from agent.enums import AgentType

class ImageAgentState(TypedDict, total=False):
    """分隔用户输入、可信运行上下文和图片业务中间结果。"""

    messages: Annotated[list[BaseMessage], add_messages]
    original_request: str
    resume_answers: dict[str, Any]
    agent: AgentType
    principal_id: str
    conversation_id: str
    run_id: str
    task_result_id: str
    attachment_ids: list[str]
    intent_validated: bool
    validated_run_id: str
    is_image_generation: bool
    image_prompt: str
    generation_options: dict[str, Any]
    image_size_confirmed: bool
    user_visible_response: str
