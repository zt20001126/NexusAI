"""确认生图尺寸并构造其他参数追问或生图工具调用。"""

import uuid
from typing import Any

from langchain_core.messages import AIMessage

from agent.constants import MAX_QUESTIONS_PER_BATCH
from agents.image_agent.parameter_policy import (
    SIZE_CHOICES,
    SIZE_QUESTION_OPTIONS,
    apply_answers,
)
from agents.image_agent.schemas import ImageGenerationOptions
from agents.image_agent.state import ImageAgentState


async def ask_node(state: ImageAgentState) -> dict[str, object]:
    """仅在用户未指定图片画幅时提问，其余参数读取主动提供值或使用默认值。

    输入：商品提示词、用户文本、上传附件标识、已知参数和恢复答案。
    输出：ask_image_parameters 或 generate_image 工具调用及完整服务端上下文。
    下一节点：tool_node，追问工具会使运行暂停，生成工具会继续至结果节点。
    """
    options = apply_answers(
        state.get("generation_options", {}),
        state.get("resume_answers", {}),
    )
    questions: list[dict[str, Any]] = []
    original_request = state.get("original_request", "")

    resume_answers = state.get("resume_answers", {})
    image_size_confirmed = state.get("image_size_confirmed", False)
    if resume_answers.get("image_size") in SIZE_CHOICES:
        image_size_confirmed = True
    if options.get("size") is not None or options.get("generate_max_pixels") is not None:
        image_size_confirmed = True
    if not image_size_confirmed:
        questions.append(
            {
                "id": "image_size",
                "title": "请选择本次生成图片的画幅比例。",
                "type": "SingleChoice",
                "options": SIZE_QUESTION_OPTIONS,
                "allow_custom_input": False,
            }
        )

    context = {
        "task_result_id": state.get("task_result_id", ""),
        "principal_id": state.get("principal_id", ""),
        "conversation_id": state.get("conversation_id", ""),
        "run_id": state.get("run_id", ""),
        "prompt": state.get("image_prompt", original_request),
        "attachment_ids": state.get("attachment_ids", []),
        "options": options,
    }
    if questions:
        question_batch = questions[:MAX_QUESTIONS_PER_BATCH]
        call = {
            "name": "ask_image_parameters",
            "args": {"questions": question_batch, **context},
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
    else:
        checked_options = ImageGenerationOptions(**options).validate_parameter_exclusivity()
        generate_context = {
            key: value for key, value in context.items() if key != "options"
        }
        call = {
            "name": "generate_image",
            "args": {
                **generate_context,
                "prompt": state.get("image_prompt", original_request),
                "attachment_ids": state.get("attachment_ids", []),
                **checked_options.model_dump(exclude_none=True),
            },
            "id": uuid.uuid4().hex,
            "type": "tool_call",
        }
    return {
        "messages": [AIMessage(content="", tool_calls=[call])],
        "generation_options": options,
        "image_size_confirmed": image_size_confirmed,
    }
