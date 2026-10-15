"""校验消息是否明确请求生成淘宝电商图片。"""

from agents.image_agent.state import ImageAgentState

IMAGE_TERMS = ("图片", "主图", "商品图", "展示图", "详情页图", "详情图", "生图")
GENERATION_TERMS = ("生成", "制作", "设计", "画", "做", "需要", "帮我")


async def validation_node(state: ImageAgentState) -> dict[str, object]:
    """识别生图意图并准备文档字段；无关内容只进入引导对话。

    输入：原始用户文本与可恢复的已验证状态。
    输出：意图标记和可从原文安全提取的 API 参数。
    下一节点：chat_node，根据意图决定结束或继续生成流程。
    """
    run_id = state.get("run_id")
    if (
        state.get("intent_validated")
        and isinstance(run_id, str)
        and run_id
        and state.get("validated_run_id") == run_id
    ):
        return {}

    from agents.image_agent.parameter_policy import extract_documented_options

    request = state.get("original_request", "").strip()[:20_000]
    has_image_term = any(term in request for term in IMAGE_TERMS)
    has_generation_term = any(term in request for term in GENERATION_TERMS)
    is_image_generation = has_image_term and has_generation_term
    options = extract_documented_options(request) if is_image_generation else {}
    return {
        "original_request": request,
        "intent_validated": True,
        "validated_run_id": run_id or "",
        "is_image_generation": is_image_generation,
        "image_prompt": "",
        "generation_options": options,
    }
