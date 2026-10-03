"""输入规范化节点。"""

from agent.state import AgentState


async def validation_node(state: AgentState) -> dict[str, str]:
    """规范化原始请求，确保后续节点只处理有界的非空文本。"""
    request = state.get("original_request", "").strip()
    return {"original_request": request[:20_000]}
