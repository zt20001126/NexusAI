"""多智能体发现、聊天、图片上传及生成结果接口。"""

import asyncio
import re
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response
from sse_starlette import EventSourceResponse

from agent.constants import IMAGE_AGENT
from agent.constants import LITERATURE_READER_AGENT
from agent.schemas.task_result import TaskResultStatus
from infra.object_storage import ObjectStorageError, ObjectStorageNotConfiguredError
from agent.streaming import encode_sse_events
from app.dependencies.auth import get_principal_id
from app.schemas.agent import ChatRequest, ResumeRequest
from agents.listing_agent.constants import LISTING_AGENT

router = APIRouter(tags=["智能体"])


def _success(data: Any) -> dict[str, Any]:
    """构造项目统一成功响应。"""
    return {"success": True, "data": data}


@router.get("/api/agents")
def list_agents(request: Request) -> dict[str, Any]:
    """列出显式注册的智能体及其聊天能力。"""
    definitions = request.app.state.agent_registry.list_definitions()
    return _success(
        [
            {
                "agent": item.agent,
                "name": item.name,
                "description": item.description,
                "supports_image_upload": item.supports_image_upload,
                "supports_document_upload": item.supports_document_upload,
            }
            for item in definitions
        ]
    )


@router.post("/api/agents/{agent}/chat")
async def chat(
    agent: str,
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """执行指定智能体的非流式对话。"""
    registry = request.app.state.agent_registry
    definition = registry.get_definition(agent)
    if agent == LITERATURE_READER_AGENT:
        raise HTTPException(status_code=400, detail="文献助手必须通过文献问答接口并选择文献")
    _validate_attachment_support(definition, payload.attachment_ids)
    _validate_listing_image_input(agent, payload.attachment_ids)
    service = registry.get_service(agent)
    events = await service.chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
        attachment_ids=payload.attachment_ids,
    )
    return _success([event.model_dump(mode="json") for event in events])


@router.post("/api/agents/{agent}/chat/stream")
async def stream_chat(
    agent: str,
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """通过公共 SSE 编码器流式执行指定智能体。"""
    registry = request.app.state.agent_registry
    definition = registry.get_definition(agent)
    if agent == LITERATURE_READER_AGENT:
        raise HTTPException(status_code=400, detail="文献助手必须通过文献问答接口并选择文献")
    _validate_attachment_support(definition, payload.attachment_ids)
    _validate_listing_image_input(agent, payload.attachment_ids)
    service = registry.get_service(agent)
    record, events = service.submit_chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
        request_id=payload.request_id or uuid.uuid4().hex,
        attachment_ids=payload.attachment_ids,
    )
    return EventSourceResponse(
        encode_sse_events(events),
        ping=None,
        headers={
            "X-Conversation-ID": record.conversation_id,
            "X-Run-ID": record.run_id,
            "Cache-Control": "no-cache",
        },
    )


@router.get("/api/agents/listen/{conversation_id}")
async def listen_agent_run(
    conversation_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    run_id: str | None = Query(default=None, pattern=r"^[1-9][0-9]{0,18}$"),
    after: str | None = Query(default=None, max_length=40),
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """授权后从共享事件流按游标恢复监听；断开只关闭本读取器。"""
    header_cursor = request.headers.get("last-event-id")
    cursor = header_cursor if header_cursor is not None else after
    if cursor is not None and re.fullmatch(r"[0-9]+-[0-9]+", cursor) is None:
        raise HTTPException(status_code=400, detail="事件游标格式不合法")
    events = request.app.state.agent_session_service.listen(
        conversation_id=conversation_id,
        principal_id=principal_id,
        run_id=run_id,
        after=cursor,
        allow_missing_at_latest=(
            request.headers.get("x-agent-history-loaded", "").lower() == "true"
        ),
    )
    return EventSourceResponse(encode_sse_events(events), ping=None, headers={"Cache-Control": "no-cache"})


@router.get("/api/agents/conversation/active/latest")
def get_latest_active_agent_run(
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """返回当前主体最新一个后台运行；并行运行时返回列表供逐会话管理。"""
    items = request.app.state.agent_session_service.active_runs(principal_id)
    return _success(items[0] if items else None)


@router.post("/api/agents/{agent}/runs/{run_id}/resume")
async def resume_run(
    agent: str,
    run_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    payload: ResumeRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """向指定智能体提交结构化答案并恢复原运行。"""
    service = request.app.state.agent_registry.get_service(agent)
    record, events = service.submit_resume(
        conversation_id=payload.conversation_id,
        run_id=run_id,
        answers=payload.answers,
        principal_id=principal_id,
        request_id=payload.request_id or uuid.uuid4().hex,
        after=payload.after_event_id,
    )
    return EventSourceResponse(
        encode_sse_events(events),
        ping=None,
        headers={
            "X-Conversation-ID": record.conversation_id,
            "X-Run-ID": record.run_id,
            "Cache-Control": "no-cache",
        },
    )


@router.post("/api/agents/{agent}/runs/{run_id}/cancel")
def cancel_run(
    agent: str,
    run_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """取消属于当前主体且仍在执行的指定智能体运行。"""
    request.app.state.agent_registry.get_service(agent).cancel(
        run_id=run_id,
        principal_id=principal_id,
    )
    return _success({"run_id": run_id, "cancel_requested": True})


@router.post("/api/uploads/images")
async def upload_reference_image(
    request: Request,
    agent: str = Query(default=IMAGE_AGENT.value, min_length=1, max_length=64),
    file_name: str = Query(default="reference-image", max_length=255),
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """接收单个原始 PNG/JPEG 请求体并暂存为用户私有附件。"""
    definition = request.app.state.agent_registry.get_definition(agent)
    if not definition.supports_image_upload:
        raise HTTPException(status_code=400, detail="该智能体不支持图片上传")

    max_bytes = request.app.state.settings.image_upload_max_bytes
    declared_length = request.headers.get("content-length")
    if declared_length is not None:
        try:
            if int(declared_length) > max_bytes:
                raise HTTPException(
                    status_code=413,
                    detail="参考图片超过服务端上限（单张最多 5 MiB）",
                )
        except ValueError:
            raise HTTPException(status_code=400, detail="Content-Length 格式不合法") from None

    chunks: list[bytes] = []
    total_bytes = 0
    async for chunk in request.stream():
        total_bytes += len(chunk)
        if total_bytes > max_bytes:
            raise HTTPException(
                status_code=413,
                detail="参考图片超过服务端上限（单张最多 5 MiB）",
            )
        chunks.append(chunk)
    image_data = b"".join(chunks)
    mime_type = _detect_image_type(image_data)
    if mime_type is None:
        raise HTTPException(status_code=415, detail="仅支持 PNG 和 JPEG 图片")

    safe_name = _safe_file_name(file_name, mime_type)
    try:
        record = await asyncio.to_thread(
            request.app.state.attachment_store.save,
            principal_id,
            safe_name,
            mime_type,
            image_data,
        )
    except ObjectStorageNotConfiguredError as error:
        raise HTTPException(status_code=503, detail=str(error)) from None
    except ObjectStorageError:
        raise HTTPException(status_code=502, detail="参考图片保存失败，请稍后重试") from None
    return _success(
        {
            "attachment_id": record.attachment_id,
            "file_name": record.file_name,
            "mime_type": record.mime_type,
            "file_size": record.file_size,
        }
    )


@router.get("/api/task-results/{task_result_id}/image")
def get_task_result_image(
    task_result_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> Response:
    """按可信用户读取成功保存的图片，越权和不存在都返回 404。"""
    record = request.app.state.task_result_store.get_owned(task_result_id, principal_id)
    outputs = record.result_data.get("outputs", []) if record is not None else []
    first_output = (
        outputs[0]
        if isinstance(outputs, list)
        and outputs
        and isinstance(outputs[0], dict)
        else {}
    )
    object_key = first_output.get("object_key")
    mime_type = first_output.get("mime_type")
    if (
        record is None
        or record.generation_status != TaskResultStatus.SUCCEEDED
        or not isinstance(object_key, str)
        or not isinstance(mime_type, str)
    ):
        raise HTTPException(status_code=404, detail="图片结果不存在")
    try:
        image_data, stored_mime_type = request.app.state.attachment_store.read_result(
            object_key,
            principal_id,
        )
    except ObjectStorageError:
        raise HTTPException(status_code=502, detail="图片暂时无法读取，请稍后重试") from None
    return Response(
        content=image_data,
        media_type=stored_mime_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/api/task-results/{task_result_id}")
def get_task_result(
    task_result_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """按可信主体读取允许公开的完整 Listing 或 Research 结果。"""
    result = request.app.state.task_result_service.get_task_result(
        task_result_id=task_result_id,
        principal_id=principal_id,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="任务结果不存在")
    return _success(result.model_dump(mode="json"))


def _detect_image_type(image_data: bytes) -> str | None:
    """检查允许的文件签名，避免只凭扩展名或 MIME 信任上传内容。"""
    if image_data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if image_data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    return None


def _validate_attachment_support(definition: Any, attachment_ids: list[str]) -> None:
    """只允许声明支持图片输入的智能体接收图片附件。"""
    if attachment_ids and not definition.supports_image_upload:
        raise HTTPException(status_code=400, detail="该智能体不支持图片上传")


def _validate_listing_image_input(agent: str, attachment_ids: list[str]) -> None:
    """Listing 必须从至少一张商品图片开始，避免缺少视觉识别的空任务。"""
    if agent == LISTING_AGENT and not attachment_ids:
        raise HTTPException(status_code=422, detail="Listing 生成需要至少上传一张商品图片")


def _safe_file_name(file_name: str, mime_type: str) -> str:
    """移除路径和控制字符，并为显示名称补充可信扩展名。"""
    leaf_name = file_name.replace("\\", "/").split("/")[-1]
    visible_name = "".join(character for character in leaf_name if character.isprintable())
    visible_name = visible_name.strip()[:120] or "reference-image"
    extension = ".png" if mime_type == "image/png" else ".jpg"
    stem, separator, supplied_extension = visible_name.rpartition(".")
    if separator and supplied_extension.lower() in {"png", "jpg", "jpeg"}:
        visible_name = f"{stem}{extension}"
    else:
        visible_name = f"{visible_name}{extension}"
    return visible_name
