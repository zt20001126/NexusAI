"""通过 TokenHub 多模态 Chat Completions 识别商品图片和包装文字。"""

import base64
from typing import Any

import httpx

from agent.constants import (
    MAX_REFERENCE_IMAGE_BYTES,
    MAX_REFERENCE_IMAGE_COUNT,
    MAX_REFERENCE_IMAGE_TOTAL_BYTES,
)
from agents.listing_agent.prompts import VISION_PROMPT
from agents.listing_agent.schemas import ListingImageAnalysis
from infra.settings import AppSettings

VISION_CHAT_ENDPOINT = "/v1/chat/completions"


class TokenHubVisionError(Exception):
    """视觉 Provider 返回的安全、稳定错误。"""

    def __init__(self, code: str, message: str) -> None:
        """只保留可安全展示的错误，不包含上游响应正文。"""
        super().__init__(message)
        self.code = code
        self.public_message = message


class TokenHubVisionClient:
    """管理视觉模型鉴权、图片边界、调用超时和 JSON 校验。"""

    def __init__(
        self,
        settings: AppSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """注入应用设置和可选 HTTP transport。"""
        self._settings = settings
        self._transport = transport

    async def analyze(
        self,
        reference_images: list[tuple[str, bytes]],
    ) -> ListingImageAnalysis:
        """识别最多三张 PNG/JPEG 商品图，响应必须符合图片观察 Schema。"""
        api_key = self._settings.tokenhub_api_key.get_secret_value()
        if not api_key:
            raise TokenHubVisionError(
                "TOKENHUB_NOT_CONFIGURED",
                "商品图片识别服务尚未完成配置，请联系管理员。",
            )
        total_bytes = sum(len(data) for _, data in reference_images)
        if (
            not reference_images
            or len(reference_images) > MAX_REFERENCE_IMAGE_COUNT
            or any(len(data) > MAX_REFERENCE_IMAGE_BYTES for _, data in reference_images)
            or total_bytes > MAX_REFERENCE_IMAGE_TOTAL_BYTES
            or any(mime not in {"image/png", "image/jpeg"} for mime, _ in reference_images)
        ):
            raise TokenHubVisionError(
                "REFERENCE_IMAGE_LIMIT_EXCEEDED",
                "请上传 1 至 3 张 PNG/JPEG 商品图片，每张不超过 5 MiB。",
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": VISION_PROMPT}]
        for mime_type, image_data in reference_images:
            encoded = base64.b64encode(image_data).decode("ascii")
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )

        endpoint = self._settings.tokenhub_base_url.rstrip("/") + VISION_CHAT_ENDPOINT
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._settings.tokenhub_timeout_seconds),
                transport=self._transport,
            ) as client:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "model": self._settings.tokenhub_vision_model,
                        "messages": [{"role": "user", "content": content}],
                        "stream": False,
                    },
                )
        except httpx.TimeoutException:
            raise TokenHubVisionError(
                "TOKENHUB_TIMEOUT", "商品图片识别超时，请稍后重试。"
            ) from None
        except httpx.HTTPError:
            raise TokenHubVisionError(
                "TOKENHUB_CONNECTION_FAILED", "暂时无法连接商品图片识别服务。"
            ) from None

        if response.status_code == 401:
            raise TokenHubVisionError(
                "TOKENHUB_AUTH_FAILED", "商品图片识别服务鉴权失败，请联系管理员。"
            )
        if response.status_code == 429:
            raise TokenHubVisionError(
                "TOKENHUB_RATE_LIMITED", "商品图片识别请求较多，请稍后重试。"
            )
        if response.status_code >= 500:
            raise TokenHubVisionError(
                "TOKENHUB_UNAVAILABLE", "商品图片识别服务暂时不可用，请稍后重试。"
            )
        if response.is_error:
            raise TokenHubVisionError(
                "TOKENHUB_REQUEST_REJECTED", "商品图片识别请求未被服务接受。"
            )

        try:
            body = response.json()
            content_text = body["choices"][0]["message"]["content"]
            if not isinstance(content_text, str):
                raise TypeError("视觉模型内容格式不正确")
            return _parse_json_content(content_text, ListingImageAnalysis)
        except (KeyError, IndexError, TypeError, ValueError):
            raise TokenHubVisionError(
                "TOKENHUB_INVALID_RESPONSE", "商品图片识别结果无法解析，请稍后重试。"
            ) from None


def _parse_json_content(content: str, schema: type[ListingImageAnalysis]) -> ListingImageAnalysis:
    """去除可选代码围栏并进行严格 Schema 校验。"""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3 and lines[-1].strip() == "```":
            text = "\n".join(lines[1:-1]).strip()
    return schema.model_validate_json(text)
