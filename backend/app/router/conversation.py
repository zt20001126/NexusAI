"""会话列表与消息历史查询接口。"""

from typing import Any

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Query, Request
from fastapi.responses import Response

from agent.errors import AttachmentAccessDeniedError, ConversationAccessDeniedError
from infra.object_storage import ObjectStorageError

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
    conversation_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    limit: int = Query(default=50, ge=1, le=100, description="每页消息数量"),
    before_message_id: str | None = Query(
        default=None,
        pattern=r"^[1-9][0-9]{0,18}$",
        description="向更早消息翻页时使用的消息 ID",
    ),
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """返回会话消息历史；响应中的消息按旧到新排列。"""
    data = _service(request).list_messages(
        conversation_id=conversation_id,
        principal_id=principal_id,
        limit=limit,
        before_message_id=before_message_id,
    )
    return _success(data.model_dump(mode="json"))


@router.get("/{conversation_id}/messages/{message_id}/attachments/{attachment_id}/image")
def get_message_attachment_image(
    conversation_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    message_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    attachment_id: Annotated[str, Path(pattern=r"^(?:[1-9][0-9]{0,18}|[0-9a-f]{32})$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> Response:
    """仅向消息所属用户提供私有上传图片。"""
    try:
        image_data, mime_type = _service(request).read_message_attachment(
            conversation_id=conversation_id,
            message_id=message_id,
            attachment_id=attachment_id,
            principal_id=principal_id,
        )
    except (AttachmentAccessDeniedError, ConversationAccessDeniedError):
        raise HTTPException(status_code=404, detail="图片不存在") from None
    except ObjectStorageError:
        raise HTTPException(status_code=502, detail="图片暂时无法读取，请稍后重试") from None
    return Response(
        content=image_data,
        media_type=mime_type,
        headers={"Cache-Control": "private, max-age=3600", "X-Content-Type-Options": "nosniff"},
    )
