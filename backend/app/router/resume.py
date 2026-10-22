"""简历助手整体保存、私有证件照与 PDF 导出接口。"""

import asyncio
import re
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Request, UploadFile
from fastapi.responses import Response

from app.dependencies.auth import get_principal_id
from app.exceptions.resume import (
    ResumePhotoInvalidError,
    ResumePhotoInvalidIdError,
    ResumePhotoTooLargeError,
)
from app.schemas.resume import (
    MAX_RESUME_PHOTO_BYTES,
    ResumePhotoUploadResponse,
    ResumeSaveRequest,
)

router = APIRouter(prefix="/api/resume", tags=["简历助手"])


def _success(data: Any) -> dict[str, Any]:
    return {"success": True, "data": data}


@router.get("")
def get_resume(
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """读取当前登录主体的简历；首次访问返回空 DTO 且不写数据库。"""
    result = request.app.state.resume_service.get_resume(
        principal_id
    )
    return _success(result.model_dump(mode="json"))


@router.put("")
def save_resume(
    payload: ResumeSaveRequest,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """整体校验并保存简历内容和排版设置。"""
    result = request.app.state.resume_service.save_resume(
        principal_id,
        payload,
    )
    return _success(result.model_dump(mode="json"))


@router.post("/photo")
async def upload_resume_photo(
    request: Request,
    file: Annotated[UploadFile, File(description="PNG/JPEG 证件照，最大 5 MiB")],
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """有界读取照片并保存至当前登录主体的 OSS staging 前缀。"""
    chunks: list[bytes] = []
    total_bytes = 0
    try:
        while block := await file.read(min(1_048_576, MAX_RESUME_PHOTO_BYTES + 1 - total_bytes)):
            total_bytes += len(block)
            if total_bytes > MAX_RESUME_PHOTO_BYTES:
                raise ResumePhotoTooLargeError()
            chunks.append(block)
        if not chunks:
            raise ResumePhotoInvalidError("照片文件不能为空")
        result: ResumePhotoUploadResponse = await asyncio.to_thread(
            request.app.state.resume_service.upload_photo,
            principal_id,
            b"".join(chunks),
        )
    finally:
        await file.close()
    return _success(result.model_dump(mode="json"))


@router.get("/photo")
def get_resume_photo(
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> Response:
    """只读取数据库当前 photo_id 引用的私有照片。"""
    data, mime_type = request.app.state.resume_service.get_saved_photo(
        principal_id
    )
    return Response(
        content=data,
        media_type=mime_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.delete("/photo")
def delete_staged_resume_photo(
    photo_id: str,
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> dict[str, Any]:
    """取消未保存的照片上传；不接受对象键，也不删除已引用照片。"""
    if not re.fullmatch(r"[0-9a-f]{32}", photo_id):
        raise ResumePhotoInvalidIdError()
    request.app.state.resume_service.delete_staged_photo(
        principal_id,
        photo_id,
    )
    return _success({"photo_id": photo_id, "deleted": True})


@router.get("/export/pdf")
def export_resume_pdf(
    request: Request,
    principal_id: str = Depends(get_principal_id),
) -> Response:
    """仅从数据库已保存版本生成 PDF，不接受临时草稿内容。"""
    pdf_bytes = request.app.state.resume_service.export_pdf(
        principal_id
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'attachment; filename="resume.pdf"',
            "X-Content-Type-Options": "nosniff",
        },
    )
