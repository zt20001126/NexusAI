"""规范化本轮图片智能体输入并清除旧运行的意图状态。"""

from agents.image_agent.constants import IMAGE_REQUEST_MAX_LENGTH
from agents.image_agent.state import ImageAgentState


async def validation_node(state: ImageAgentState) -> dict[str, object]:
    """按运行轮次重置模型判断和生图参数；不负责猜测用户意图。

    输入：共享运行器提供的原始用户文本和运行标识。
    输出：有界请求文本、清空后的意图和提示词状态。
    下一节点：chat_node，由注入的模型判断本轮语义。
    """
    run_id = state.get("run_id")
    if (
        state.get("intent_validated")
        and isinstance(run_id, str)
        and run_id
        and state.get("validated_run_id") == run_id
    ):
        return {}

    request = state.get("original_request", "").strip()[:IMAGE_REQUEST_MAX_LENGTH]
    return {
        "original_request": request,
        "intent_validated": False,
        "validated_run_id": "",
        "is_image_generation": False,
        "image_prompt": "",
        "generation_options": {},
    }
