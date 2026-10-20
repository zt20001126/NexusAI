"""在 FastAPI 解析 JSON 或 multipart 前限制简历请求体大小。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

from app.schemas.resume import MAX_RESUME_JSON_BYTES, MAX_RESUME_PHOTO_REQUEST_BYTES

ASGIReceive = Callable[[], Awaitable[dict[str, Any]]]
ASGISend = Callable[[dict[str, Any]], Awaitable[None]]


class ResumeRequestSizeLimitMiddleware:
    """仅为简历 PUT 与照片上传预读有界请求体，并为简历响应禁用缓存。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict[str, Any], receive: ASGIReceive, send: ASGISend) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        path = str(scope.get("path", "")).rstrip("/")
        method = str(scope.get("method", "")).upper()
        limit = _request_limit(path, method)
        wrapped_send = _cache_control_send(path, send)
        if limit is None:
            await self.app(scope, receive, wrapped_send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > limit:
                    await _send_too_large(wrapped_send)
                    return
            except ValueError:
                await _send_too_large(wrapped_send)
                return

        chunks: list[bytes] = []
        total = 0
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            chunk = message.get("body", b"")
            total += len(chunk)
            if total > limit:
                await _send_too_large(wrapped_send)
                return
            chunks.append(chunk)
            if not message.get("more_body", False):
                break

        body = b"".join(chunks)
        delivered = False

        async def replay_receive() -> dict[str, Any]:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        await self.app(scope, replay_receive, wrapped_send)


def _request_limit(path: str, method: str) -> int | None:
    if path == "/api/resume" and method == "PUT":
        return MAX_RESUME_JSON_BYTES
    if path == "/api/resume/photo" and method == "POST":
        return MAX_RESUME_PHOTO_REQUEST_BYTES
    return None


def _cache_control_send(path: str, send: ASGISend) -> ASGISend:
    async def wrapped(message: dict[str, Any]) -> None:
        if path.startswith("/api/resume") and message.get("type") == "http.response.start":
            headers = list(message.get("headers", []))
            if not any(key.lower() == b"cache-control" for key, _ in headers):
                headers.append((b"cache-control", b"private, no-store"))
            message = {**message, "headers": headers}
        await send(message)

    return wrapped


async def _send_too_large(send: ASGISend) -> None:
    payload = json.dumps(
        {
            "success": False,
            "code": "REQUEST_TOO_LARGE",
            "message": "请求体超过简历助手允许的大小",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(payload)).encode("ascii")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": payload})
