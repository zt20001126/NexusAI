"""智能体发现、对话、恢复和取消 API。"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from sse_starlette import EventSourceResponse

from agent_core.streaming import encode_sse_events
from app.dependencies import get_principal_id
from app.schemas import AgentInfo, ChatRequest, ResumeRequest
from app.service import AgentApplicationService

router = APIRouter(prefix="/api/agents", tags=["通用智能体"])


def _service(request: Request) -> AgentApplicationService:
    """从应用生命周期状态获取唯一应用编排服务。"""
    return request.app.state.agent_service


def _success(data: Any) -> dict[str, Any]:
    """为普通 JSON API 构造统一成功响应。"""
    return {"success": True, "data": data}


@router.get("")
async def list_agents(request: Request) -> dict[str, Any]:
    """列出当前进程注册的业务智能体。"""
    agents = [
        AgentInfo(
            agent_id=item.agent_id,
            name=item.name,
            description=item.description,
        ).model_dump()
        for item in _service(request).list_agents()
    ]
    return _success(agents)


@router.post("/{agent_id}/chat")
async def chat(
    agent_id: str,
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """执行一次非流式对话并返回完整事件列表。"""
    events = await _service(request).chat(
        agent_id=agent_id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
    )
    return _success([event.model_dump(mode="json") for event in events])


@router.post("/{agent_id}/chat/stream")
async def stream_chat(
    agent_id: str,
    payload: ChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """通过 SSE 执行智能体，不透传 LangGraph 的内部事件结构。"""
    events = _service(request).stream_chat(
        agent_id=agent_id,
        message=payload.message,
        conversation_id=payload.conversation_id,
        principal_id=principal_id,
    )
    return EventSourceResponse(encode_sse_events(events), ping=None)


@router.post("/{agent_id}/runs/{run_id}/resume")
async def resume_run(
    agent_id: str,
    run_id: str,
    payload: ResumeRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """提交结构化答案并以 SSE 继续等待中的运行。"""
    events = _service(request).resume(
        agent_id=agent_id,
        conversation_id=payload.conversation_id,
        run_id=run_id,
        answers=payload.answers,
        principal_id=principal_id,
    )
    return EventSourceResponse(encode_sse_events(events), ping=None)


@router.post("/{agent_id}/runs/{run_id}/cancel")
async def cancel_run(
    agent_id: str,
    run_id: str,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """取消属于当前可信主体且仍在执行的运行。"""
    _service(request).cancel(
        agent_id=agent_id,
        run_id=run_id,
        principal_id=principal_id,
    )
    return _success({"run_id": run_id, "cancel_requested": True})
