"""TokenHub Hy-Image-3.5-preview 同步生图 API 客户端。"""

import base64
from typing import Any

import httpx

from agent.constants import (
    MAX_REFERENCE_IMAGE_BYTES,
    MAX_REFERENCE_IMAGE_COUNT,
    MAX_REFERENCE_IMAGE_TOTAL_BYTES,
)
from agents.image_agent.constants import DEFAULT_REFERENCE_RESIZE_MAX_PIXELS
from agents.image_agent.schemas import ImageGenerationOptions, TokenHubImageResult
from infra.settings import AppSettings


class TokenHubImageError(Exception):
    """TokenHub 外部调用失败的受控错误信息。"""

    def __init__(self, code: str, message: str, request_id: str | None = None) -> None:
        """保存可展示错误和服务端排障标识，不包含上游原始异常文本。"""
        super().__init__(message)
        self.code = code
        self.public_message = message
        self.request_id = request_id


class TokenHubImageClient:
    """管理 TokenHub 鉴权、请求超时、响应校验和安全错误映射。"""

    def __init__(
        self,
        settings: AppSettings,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """注入设置与可选 HTTP transport，测试可使用 MockTransport。"""
        self._settings = settings
        self._transport = transport

    async def generate(
        self,
        *,
        prompt: str,
        reference_images: list[tuple[str, bytes]],
        options: ImageGenerationOptions,
        session_id: str,
    ) -> TokenHubImageResult:
        """构建 Hy-Image-3.5-preview 请求并解析最终交付图。"""
        api_key = self._settings.tokenhub_api_key.get_secret_value()
        if not api_key:
            raise TokenHubImageError(
                "TOKENHUB_NOT_CONFIGURED",
                "图片生成服务尚未完成配置，请联系管理员。",
            )

        if (
            len(reference_images) > MAX_REFERENCE_IMAGE_COUNT
            or any(
                len(image_data) > MAX_REFERENCE_IMAGE_BYTES
                for _, image_data in reference_images
            )
        ):
            raise TokenHubImageError(
                "REFERENCE_IMAGE_LIMIT_EXCEEDED",
                "参考图最多上传 3 张，每张不能超过 5 MiB。",
            )
        total_reference_bytes = sum(len(image_data) for _, image_data in reference_images)
        if total_reference_bytes > MAX_REFERENCE_IMAGE_TOTAL_BYTES:
            raise TokenHubImageError(
                "REFERENCE_IMAGE_LIMIT_EXCEEDED",
                "参考图总大小超出请求上限。",
            )

        content: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
        for mime_type, image_data in reference_images:
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{mime_type};base64,"
                            f"{base64.b64encode(image_data).decode('ascii')}"
                    },
                }
            )

        request_body: dict[str, Any] = {
            "model": self._settings.tencent_hy_image_model,
            "messages": [{"role": "user", "content": content}],
            "session": session_id,
        }
        if options.size is not None:
            request_body["size"] = options.size
        if options.generate_max_pixels is not None:
            request_body["generate_max_pixels"] = options.generate_max_pixels
        if reference_images:
            request_body["resize_max_pixels"] = (
                options.resize_max_pixels or DEFAULT_REFERENCE_RESIZE_MAX_PIXELS
            )
        if options.seed is not None:
            request_body["seed"] = options.seed
        if options.footnote is not None:
            request_body["footnote"] = options.footnote
        if options.use_search_tool:
            request_body["use_search_tool"] = {"value": True}

        endpoint = (
            self._settings.tokenhub_base_url.rstrip("/")
            + "/"
            + self._settings.tencent_hy_image_endpoint.lstrip("/")
        )
        timeout = httpx.Timeout(self._settings.tokenhub_timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            transport=self._transport,
        ) as client:
            try:
                response = await client.post(
                    endpoint,
                    headers={"Authorization": f"Bearer {api_key}"},
                    json=request_body,
                )
            except httpx.TimeoutException as error:
                raise TokenHubImageError(
                    "TOKENHUB_TIMEOUT",
                    "图片生成服务响应超时，请稍后重试。",
                ) from error
            except httpx.HTTPError as error:
                raise TokenHubImageError(
                    "TOKENHUB_CONNECTION_FAILED",
                    "暂时无法连接图片生成服务，请稍后重试。",
                ) from error

        request_id = _read_request_id(response)
        if response.status_code == 401:
            raise TokenHubImageError(
                "TOKENHUB_AUTH_FAILED",
                "图片生成服务鉴权失败，请联系管理员。",
                request_id,
            )
        if response.status_code == 422:
            raise TokenHubImageError(
                "TOKENHUB_CONTENT_REJECTED",
                "图片请求未通过内容安全检查，请调整商品描述后重试。",
                request_id,
            )
        if response.status_code == 429:
            raise TokenHubImageError(
                "TOKENHUB_RATE_LIMITED",
                "图片生成请求较多，请稍后重试。",
                request_id,
            )
        if response.status_code >= 500:
            raise TokenHubImageError(
                "TOKENHUB_UNAVAILABLE",
                "图片生成服务暂时不可用，请稍后重试。",
                request_id,
            )
        if response.is_error:
            raise TokenHubImageError(
                "TOKENHUB_REQUEST_REJECTED",
                "图片请求参数未被图片生成服务接受。",
                request_id,
            )

        try:
            body = response.json()
            image = body["choices"][0]["delta"]["image"]
            result = TokenHubImageResult(
                image_url=image["url"],
                width=image.get("width"),
                height=image.get("height"),
                request_id=body.get("request_id") or request_id,
                provider_model=body.get("model"),
                metadata={
                    "usage_total_tokens": (
                        body.get("tokenhub_usage", {}).get("total_tokens")
                        if isinstance(body.get("tokenhub_usage"), dict)
                        else None
                    )
                },
            )
        except (KeyError, IndexError, TypeError, ValueError) as error:
            raise TokenHubImageError(
                "TOKENHUB_INVALID_RESPONSE",
                "图片生成服务返回了无法识别的结果，请稍后重试。",
                request_id,
            ) from error
        return result


def _read_request_id(response: httpx.Response) -> str | None:
    """从响应头或合法 JSON 中提取有界排障标识。"""
    request_id = response.headers.get("x-request-id")
    if request_id:
        return request_id[:256]
    try:
        body = response.json()
    except ValueError:
        return None
    value = body.get("request_id") if isinstance(body, dict) else None
    return value[:256] if isinstance(value, str) else None
