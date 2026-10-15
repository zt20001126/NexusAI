"""商品图片观察节点。"""

import asyncio
import base64
import json
from collections.abc import Callable
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from agent.constants import (
    MAX_REFERENCE_IMAGE_BYTES,
    MAX_REFERENCE_IMAGE_COUNT,
    MAX_REFERENCE_IMAGE_TOTAL_BYTES,
)
from agent.persistence.interfaces import AttachmentStore
from agents.listing_agent.prompts import VISION_PROMPT
from agents.listing_agent.schemas import ListingImageAnalysis
from agents.listing_agent.state import ListingAgentState
from agents.listing_agent.nodes._shared import _parse_model_json


def _validate_reference_images(reference_images: list[tuple[str, bytes]]) -> None:
    """在调用 DeepSeek 前复核附件数量、格式和总字节上限。"""
    total_bytes = sum(len(image_data) for _, image_data in reference_images)
    if (
        not reference_images
        or len(reference_images) > MAX_REFERENCE_IMAGE_COUNT
        or any(
            len(image_data) > MAX_REFERENCE_IMAGE_BYTES
            for _, image_data in reference_images
        )
        or total_bytes > MAX_REFERENCE_IMAGE_TOTAL_BYTES
        or any(
            mime_type not in {"image/png", "image/jpeg"}
            for mime_type, _ in reference_images
        )
    ):
        raise ValueError("请上传 1 至 3 张 PNG/JPEG 商品图片，每张不超过 5 MiB。")


def create_vision_node(
    chat_model: BaseChatModel,
    attachment_store: AttachmentStore,
) -> Callable[..., Any]:
    """创建使用项目 DeepSeek ChatModel 分析授权商品图片的节点。"""

    async def vision_node(state: ListingAgentState) -> dict[str, Any]:
        """读取已绑定图片并提取外观、包装文字和可见特征。"""
        attachment_ids = state.get("attachment_ids", [])
        if not attachment_ids:
            raise ValueError("Listing 生成需要至少一张商品图片")
        attachments = await asyncio.to_thread(
            attachment_store.list_for_generation,
            attachment_ids,
            state.get("principal_id", ""),
            state.get("conversation_id", ""),
        )
        reference_images = [(item.mime_type, item.image_data) for item in attachments]
        _validate_reference_images(reference_images)
        image_content: list[dict[str, Any]] = [
            {"type": "text", "text": "请根据系统要求观察以下商品图片。"}
        ]
        for mime_type, image_data in reference_images:
            encoded = base64.b64encode(image_data).decode("ascii")
            image_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )
        response = await chat_model.ainvoke(
            [
                SystemMessage(
                    content=(
                        VISION_PROMPT
                        + "\n输出 Schema："
                        + json.dumps(
                            ListingImageAnalysis.model_json_schema(),
                            ensure_ascii=False,
                        )
                    )
                ),
                HumanMessage(content=image_content),
            ]
        )
        analysis = _parse_model_json(response.content, ListingImageAnalysis)
        return {"image_analysis": analysis.model_dump(mode="json")}

    return vision_node
