"""限制外部地址并下载 TokenHub 最终图片到 OSS 前的图片字节。"""

from urllib.parse import urlparse

import httpx

from agents.image_agent.providers.tokenhub_client import TokenHubImageError

ALLOWED_IMAGE_DOMAIN_SUFFIX = ".myqcloud.com"
IMAGE_DOWNLOAD_CHUNK_BYTES = 64 * 1024


class ImageResultDownloader:
    """只下载 HTTPS 腾讯云对象存储域名上的图片结果。"""

    def __init__(
        self,
        *,
        timeout_seconds: int,
        max_bytes: int,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """设置下载超时、字节上限及可替换 HTTP transport。"""
        self._timeout_seconds = timeout_seconds
        self._max_bytes = max_bytes
        self._transport = transport

    async def download(self, image_url: str) -> tuple[bytes, str]:
        """校验域名、状态码、图片 MIME 和字节上限后返回图片内容。"""
        _validate_result_url(image_url)
        timeout = httpx.Timeout(self._timeout_seconds)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
        ) as client:
            try:
                async with client.stream("GET", image_url) as response:
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";")[0].lower()
                    if content_type not in {"image/png", "image/jpeg"}:
                        raise TokenHubImageError(
                            "IMAGE_RESULT_INVALID_TYPE",
                            "图片生成服务返回了不受支持的文件类型。",
                        )
                    content_length = response.headers.get("content-length")
                    if content_length and int(content_length) > self._max_bytes:
                        raise TokenHubImageError(
                            "IMAGE_RESULT_TOO_LARGE",
                            "生成图片超过系统允许的保存大小。",
                        )
                    chunks: list[bytes] = []
                    total_bytes = 0
                    async for chunk in response.aiter_bytes(IMAGE_DOWNLOAD_CHUNK_BYTES):
                        total_bytes += len(chunk)
                        if total_bytes > self._max_bytes:
                            raise TokenHubImageError(
                                "IMAGE_RESULT_TOO_LARGE",
                                "生成图片超过系统允许的保存大小。",
                            )
                        chunks.append(chunk)
            except TokenHubImageError:
                raise
            except (httpx.HTTPError, ValueError) as error:
                raise TokenHubImageError(
                    "IMAGE_RESULT_DOWNLOAD_FAILED",
                    "图片已生成，但暂时无法保存结果，请稍后重试。",
                ) from error
        if not chunks:
            raise TokenHubImageError(
                "IMAGE_RESULT_EMPTY",
                "图片生成服务返回了空图片，请稍后重试。",
            )
        return b"".join(chunks), content_type


def _validate_result_url(image_url: str) -> None:
    """拒绝非 HTTPS、非腾讯云域名和本地网络地址。"""
    parsed = urlparse(image_url)
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(ALLOWED_IMAGE_DOMAIN_SUFFIX)
        or hostname == "myqcloud.com"
        or parsed.username is not None
        or parsed.password is not None
    ):
        raise TokenHubImageError(
            "IMAGE_RESULT_URL_REJECTED",
            "图片生成服务返回了无法安全读取的图片地址。",
        )
