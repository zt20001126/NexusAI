"""PDF 文献库管理、历史文献选择和文献 SSE 问答接口。"""

import asyncio
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, HTTPException, Path, Query, Request, UploadFile
from sse_starlette import EventSourceResponse

from agent.streaming import encode_sse_events
from app.dependencies.auth import get_principal_id
from app.schemas.literature import (
    LiteratureChatRequest,
    UpdateConversationLiteratureDocumentsRequest,
)


router = APIRouter(prefix="/api/v1/literature", tags=["文献解读助手"])


def _success(data: Any) -> dict[str, Any]:
    """为文献管理 JSON API 构造统一成功响应。"""
    return {"success": True, "data": data}


@router.post("/documents", status_code=202)
async def upload_document(
    request: Request,
    file: Annotated[UploadFile, File(description="待导入的 PDF 文献")],
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """以 multipart 接收 PDF，进行体积边界检查并交由应用服务排队。"""
    max_bytes = request.app.state.settings.literature_upload_max_bytes
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        while block := await file.read(min(1_048_576, max_bytes + 1 - total_bytes)):
            total_bytes += len(block)
            if total_bytes > max_bytes:
                raise HTTPException(status_code=413, detail="PDF 超过服务端上传上限")
            chunks.append(block)
        result = await asyncio.to_thread(
            request.app.state.literature_service.upload_pdf,
            principal_id=principal_id,
            file_name=file.filename or "literature.pdf",
            pdf_bytes=b"".join(chunks),
        )
    except ValueError as error:
        raise HTTPException(status_code=415, detail=str(error)) from None
    finally:
        await file.close()
    return _success(result.model_dump(mode="json"))


@router.get("/documents")
def list_documents(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100, description="每页文献数量"),
    offset: int = Query(default=0, ge=0, description="文献列表偏移量"),
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """返回当前可信主体的文献库和处理状态。"""
    result = request.app.state.literature_service.list_documents(
        principal_id=principal_id,
        limit=limit,
        offset=offset,
    )
    return _success(result.model_dump(mode="json"))


@router.get("/documents/{document_id}")
def get_document(
    document_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """按可信主体读取单篇文献状态和安全错误说明。"""
    result = request.app.state.literature_service.get_document(
        document_id=document_id,
        principal_id=principal_id,
    )
    return _success(result.model_dump(mode="json"))


@router.delete("/documents/{document_id}")
def delete_document(
    document_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """删除文献原件、数据库分块和历史会话文献关联。"""
    request.app.state.literature_service.delete_document(
        document_id=document_id,
        principal_id=principal_id,
    )
    return _success({"document_id": document_id, "deleted": True})


@router.post("/chat/stream")
async def stream_literature_chat(
    payload: LiteratureChatRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> EventSourceResponse:
    """按会话中已验证的文献集合运行文献助手并返回统一 SSE 事件。"""
    events = request.app.state.literature_service.stream_chat(
        message=payload.message,
        conversation_id=payload.conversation_id,
        document_ids=payload.document_ids,
        principal_id=principal_id,
    )
    return EventSourceResponse(encode_sse_events(events), ping=None)


@router.get("/conversations/{conversation_id}/documents")
def get_conversation_documents(
    conversation_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """恢复可信历史文献会话当前关联的文献选择。"""
    result = request.app.state.literature_service.get_conversation_documents(
        conversation_id=conversation_id,
        principal_id=principal_id,
    )
    return _success(result.model_dump(mode="json"))


@router.put("/conversations/{conversation_id}/documents")
def update_conversation_documents(
    conversation_id: Annotated[str, Path(pattern=r"^[1-9][0-9]{0,18}$")],
    payload: UpdateConversationLiteratureDocumentsRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """替换历史文献会话关联文献，服务层会重复验证主体和 ready 状态。"""
    result = request.app.state.literature_service.update_conversation_documents(
        conversation_id=conversation_id,
        document_ids=payload.document_ids,
        principal_id=principal_id,
    )
    return _success(result.model_dump(mode="json"))

