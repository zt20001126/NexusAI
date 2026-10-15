"""确认生图尺寸并构造其他参数追问或生图工具调用。"""

import uuid
from typing import Any

from langchain_core.messages import AIMessage

from agents.image_agent.parameter_policy import (
    RESIZE_PIXEL_CHOICES,
    SIZE_CHOICES,
    apply_answers,
)
from agents.image_agent.schemas import ImageGenerationOptions
from agents.image_agent.state import ImageAgentState


async def ask_node(state: ImageAgentState) -> dict[str, object]:
    """每次新生图运行都询问尺寸，并按需追问其他 TokenHub 参数。

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
    if resume_answers.get("image_size") not in SIZE_CHOICES:
        questions.append(
            {
                "id": "image_size",
                "title": "图片尺寸或像素档位",
                "prompt": (
                    "请选择本次生成的尺寸或像素档位。精确尺寸与面积档位只能选一项；"
                    "智能推荐对应 1.5K 档位。每次生成都需要确认。"
                ),
                "type": "SingleChoice",
                "options": list(SIZE_CHOICES),
                "allow_custom_input": False,
            }
        )

    asks_for_footnote = any(term in original_request for term in ("水印", "脚注"))
    if asks_for_footnote and not options.get("footnote"):
        previous_footnote = state.get("resume_answers", {}).get("footnote")
        if not isinstance(previous_footnote, str) or len(previous_footnote.strip()) > 16:
            questions.append(
                {
                    "id": "footnote",
                    "title": "图片水印文字",
                    "prompt": "请输入要放在图片右下角的文字，最多 16 个字符。",
                    "type": "TextQuestion",
                    "allow_custom_input": True,
                    "placeholder": "输入水印文字",
                }
            )

    asks_for_seed = any(term in original_request.lower() for term in ("seed", "复现种子"))
    if asks_for_seed and options.get("seed") is None:
        previous_seed = state.get("resume_answers", {}).get("seed")
        previous_seed_valid = (
            isinstance(previous_seed, str)
            and previous_seed.isdigit()
            and int(previous_seed) <= 9_223_372_036_854_775_807
        )
        if not previous_seed_valid:
            questions.append(
                {
                    "id": "seed",
                    "title": "生成种子",
                    "prompt": "请输入 0 到 9223372036854775807 之间的整数，用于尝试复现生成结果。",
                    "type": "TextQuestion",
                    "allow_custom_input": True,
                    "placeholder": "输入整数 seed",
                }
            )

    asks_for_resize = any(
        term in original_request.lower()
        for term in ("resize_max_pixels", "参考图缩放", "参考图处理面积", "参考图像素")
    )
    if (
        asks_for_resize
        and state.get("attachment_ids")
        and options.get("resize_max_pixels") is None
    ):
        questions.append(
            {
                "id": "resize_max_pixels",
                "title": "参考图输入面积",
                "prompt": "参考图超过所选面积时会按比例缩放，默认值为 1K。请选择上限。",
                "type": "SingleChoice",
                "options": list(RESIZE_PIXEL_CHOICES),
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
        call = {
            "name": "ask_image_parameters",
            "args": {"questions": questions, **context},
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
    return {"messages": [AIMessage(content="", tool_calls=[call])]}
