"""唯一智能体的对话、恢复和取消 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from agent.streaming import encode_sse_events
from app.dependencies.auth import get_principal_id
from app.schemas.agent import ChatRequest, ResumeRequest
from app.service.agent import AgentApplicationService

router = APIRouter(prefix="/api/agent", tags=["通用智能体"])


def _service(request: Request) -> AgentApplicationService:
    """从应用生命周期状态获取唯一应用编排服务。"""
    return request.app.state.agent_service


def _success(data: Any) -> dict[str, Any]:
    """为普通 JSON API 构造统一成功响应。"""
    return {"success": True, "data": data}


@router.post("/chat")
async def chat(
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """执行一次非流式对话并返回完整事件列表。"""
    events = await _service(request).chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
    )
    return _success([event.model_dump(mode="json") for event in events])


@router.post("/chat/stream")
async def stream_chat(
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """通过 SSE 执行智能体，不透传 LangGraph 的内部事件结构。"""
    events = _service(request).stream_chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
    )
    return EventSourceResponse(encode_sse_events(events), ping=None)


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    payload: ResumeRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """提交结构化答案并以 SSE 继续等待中的运行。"""
    events = _service(request).resume(
        conversation_id=payload.conversation_id,
        run_id=run_id,
        answers=payload.answers,
        principal_id=principal_id,
    )
    return EventSourceResponse(encode_sse_events(events), ping=None)


@router.post("/runs/{run_id}/cancel")
async def cancel_run(
    run_id: str,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """取消属于当前可信主体且仍在执行的运行。"""
    _service(request).cancel(
        run_id=run_id,
        principal_id=principal_id,
    )
    return _success({"run_id": run_id, "cancel_requested": True})
