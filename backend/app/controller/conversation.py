"""会话列表与消息历史查询接口。"""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.dependencies.auth import get_principal_id
from app.service.conversation import ConversationApplicationService

router = APIRouter(prefix="/api/conversations", tags=["会话"])


def _service(request: Request) -> ConversationApplicationService:
    """从应用生命周期状态获取会话查询服务。"""
    return request.app.state.conversation_service


def _success(data: Any) -> dict[str, Any]:
    """为查询接口构造统一成功响应。"""
    return {"success": True, "data": data}


@router.get("")
def list_conversations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="每页会话数量"),
    offset: int = Query(default=0, ge=0, description="会话列表偏移量"),
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """返回当前可信主体的会话列表。"""
    data = _service(request).list_conversations(
        principal_id=principal_id,
        limit=limit,
        offset=offset,
    )
    return _success(data.model_dump(mode="json"))


@router.get("/{conversation_id}/messages")
def list_conversation_messages(
    conversation_id: str,
    request: Request,
    limit: int = Query(default=50, ge=1, le=100, description="每页消息数量"),
    before_sequence: int | None = Query(
        default=None,
        ge=1,
        description="向更早消息翻页时使用的消息序号",
    ),
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """返回会话消息历史；响应中的消息按旧到新排列。"""
    data = _service(request).list_messages(
        conversation_id=conversation_id,
        principal_id=principal_id,
        limit=limit,
        before_sequence=before_sequence,
    )
    return _success(data.model_dump(mode="json"))
