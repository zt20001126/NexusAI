"""编排简历读写、固定 owner、照片补偿与 PDF 导出。"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Protocol

from sqlalchemy.exc import SQLAlchemyError

from app.crud.resume import PostgresResumeRepository, ResumeRecord
from app.exceptions.resume import (
    ResumeNotFoundError,
    ResumePageOverflowError,
    ResumePdfTimeoutError,
    ResumePdfUnavailableError,
    ResumePhotoInvalidError,
    ResumePhotoNotFoundError,
    ResumePhotoStorageUnavailableError,
    ResumePhotoTooLargeError,
    ResumeStorageNotConfiguredError,
    ResumeStorageUnavailableError,
)
from app.schemas.resume import (
    ResumeContent,
    ResumePhotoUploadResponse,
    ResumeResponse,
    ResumeSaveRequest,
    ResumeStyleConfig,
)
from app.service.resume_pdf import ResumePdfRenderer, build_resume_html
from infra.resume_photo_storage import (
    ResumePhotoInvalidContentError,
    ResumePhotoObjectNotFoundError,
    ResumePhotoStorageError,
    ResumePhotoStorageNotConfiguredError,
    ResumePhotoTooLargeContentError,
)
logger = logging.getLogger(__name__)


class ResumePhotoStorage(Protocol):
    """简历照片存储所需的最小能力边界。"""

    def save_staged(self, principal_id: str, photo_id: str, data: bytes) -> str: ...

    def promote_staged(self, principal_id: str, photo_id: str) -> None: ...

    def read_final(self, principal_id: str, photo_id: str) -> tuple[bytes, str]: ...

    def delete_staged(self, principal_id: str, photo_id: str) -> None: ...

    def delete_final(self, principal_id: str, photo_id: str) -> None: ...

    def cleanup_unreferenced_final(
        self, principal_id: str, referenced_photo_id: str | None, *, min_age_seconds: int
    ) -> None: ...


class ResumeApplicationService:
    """运行首版单人简历用例，所有数据读写都绑定固定主体。"""

    def __init__(
        self,
        *,
        repository: PostgresResumeRepository,
        photo_storage: ResumePhotoStorage,
        pdf_renderer: ResumePdfRenderer,
    ) -> None:
        self._repository = repository
        self._photo_storage = photo_storage
        self._pdf_renderer = pdf_renderer

    def get_resume(self, principal_id: str) -> ResumeResponse:
        """读取已保存简历；空状态不创建用户或简历行。"""
        record = self._get_record(principal_id)
        if record is None:
            response = ResumeResponse(
                exists=False,
                content=ResumeContent(),
                style_config=ResumeStyleConfig(),
            )
            self._cleanup_orphans(principal_id, None)
            return response
        self._cleanup_orphans(
            principal_id,
            _read_photo_id(record.content),
        )
        return _to_response(record)

    def save_resume(
        self, principal_id: str, payload: ResumeSaveRequest
    ) -> ResumeResponse:
        """整体保存简历，并按数据库引用切换顺序补偿照片对象。"""
        current = self._get_record(principal_id)
        previous_photo_id = _read_photo_id(current.content) if current else None
        new_photo_id = payload.content.basic_info.photo_id
        promoted = False

        if new_photo_id and new_photo_id != previous_photo_id:
            try:
                self._photo_storage.promote_staged(principal_id, new_photo_id)
                promoted = True
            except ResumePhotoObjectNotFoundError:
                raise ResumePhotoNotFoundError() from None
            except ResumePhotoStorageNotConfiguredError:
                raise ResumeStorageNotConfiguredError() from None
            except ResumePhotoStorageError:
                raise ResumePhotoStorageUnavailableError() from None

        try:
            saved = self._repository.upsert(
                principal_id,
                content=payload.content.model_dump(mode="json", exclude_none=True),
                style_config=payload.style_config.model_dump(mode="json"),
            )
        except SQLAlchemyError:
            if promoted and new_photo_id:
                self._best_effort_delete_final(principal_id, new_photo_id)
            raise ResumeStorageUnavailableError() from None

        if previous_photo_id and previous_photo_id != new_photo_id:
            self._best_effort_delete_final(principal_id, previous_photo_id)
        if promoted and new_photo_id:
            self._best_effort_delete_staged(principal_id, new_photo_id)

        self._cleanup_orphans(principal_id, new_photo_id)
        return _to_response(saved)

    def upload_photo(
        self, principal_id: str, data: bytes
    ) -> ResumePhotoUploadResponse:
        """将有界 PNG/JPEG 文件写入 OSS staging 并返回随机引用。"""
        photo_id = uuid.uuid4().hex
        try:
            self._photo_storage.save_staged(principal_id, photo_id, data)
        except ResumePhotoTooLargeContentError as error:
            raise ResumePhotoTooLargeError() from error
        except ResumePhotoInvalidContentError as error:
            raise ResumePhotoInvalidError() from error
        except ResumePhotoStorageNotConfiguredError:
            raise ResumeStorageNotConfiguredError() from None
        except ResumePhotoStorageError:
            raise ResumePhotoStorageUnavailableError() from None
        mime_type = "image/png" if data.startswith(b"\x89PNG\r\n\x1a\n") else "image/jpeg"
        return ResumePhotoUploadResponse(
            photo_id=photo_id,
            mime_type=mime_type,
            file_size=len(data),
        )

    def get_saved_photo(self, principal_id: str) -> tuple[bytes, str]:
        """读取简历当前引用的私有照片。"""
        record = self._get_record(principal_id)
        photo_id = _read_photo_id(record.content) if record else None
        if not photo_id:
            raise ResumePhotoNotFoundError()
        try:
            return self._photo_storage.read_final(principal_id, photo_id)
        except ResumePhotoObjectNotFoundError:
            raise ResumePhotoNotFoundError() from None
        except ResumePhotoStorageNotConfiguredError:
            raise ResumeStorageNotConfiguredError() from None
        except ResumePhotoStorageError:
            raise ResumePhotoStorageUnavailableError() from None

    def delete_staged_photo(self, principal_id: str, photo_id: str) -> None:
        """只删除当前主体的暂存照片；OSS 生命周期提供过期兜底。"""
        try:
            self._photo_storage.delete_staged(principal_id, photo_id)
        except ResumePhotoObjectNotFoundError:
            # staging 已被过期生命周期删除时，让取消请求保持幂等。
            return
        except ResumePhotoStorageNotConfiguredError:
            raise ResumeStorageNotConfiguredError() from None
        except ResumePhotoStorageError:
            raise ResumePhotoStorageUnavailableError() from None

    def export_pdf(self, principal_id: str) -> bytes:
        """从数据库已保存版本生成单页 A4 PDF。"""
        record = self._get_record(principal_id)
        if record is None:
            raise ResumeNotFoundError()
        try:
            content = ResumeContent.model_validate(record.content)
            style = ResumeStyleConfig.model_validate(record.style_config)
        except Exception:
            logger.error("已保存简历 DTO 校验失败")
            raise ResumeStorageUnavailableError() from None

        photo_data_uri: str | None = None
        photo_id = content.basic_info.photo_id
        if photo_id:
            photo, mime_type = self.get_saved_photo(principal_id)
            import base64

            photo_data_uri = f"data:{mime_type};base64,{base64.b64encode(photo).decode('ascii')}"
        html = build_resume_html(content, style, photo_data_uri=photo_data_uri)
        try:
            return self._pdf_renderer.render(html)
        except ResumePageOverflowError:
            raise
        except ResumePdfTimeoutError:
            raise
        except ResumePdfUnavailableError:
            raise
        except Exception:
            logger.exception("简历 PDF 渲染失败")
            raise ResumePdfUnavailableError() from None

    def _get_record(self, principal_id: str) -> ResumeRecord | None:
        try:
            return self._repository.get(principal_id)
        except SQLAlchemyError:
            raise ResumeStorageUnavailableError() from None

    def _cleanup_orphans(self, principal_id: str, photo_id: str | None) -> None:
        try:
            self._photo_storage.cleanup_unreferenced_final(
                principal_id,
                photo_id,
                min_age_seconds=86_400,
            )
        except Exception as error:
            logger.warning(
                "简历孤儿照片清理调用失败 error_type=%s", type(error).__name__
            )

    def _best_effort_delete_final(self, principal_id: str, photo_id: str) -> None:
        try:
            self._photo_storage.delete_final(principal_id, photo_id)
        except Exception as error:
            logger.warning(
                "简历最终照片补偿删除失败 error_type=%s", type(error).__name__
            )

    def _best_effort_delete_staged(self, principal_id: str, photo_id: str) -> None:
        try:
            self._photo_storage.delete_staged(principal_id, photo_id)
        except Exception as error:
            logger.warning(
                "简历暂存照片清理失败 error_type=%s", type(error).__name__
            )


def _to_response(record: ResumeRecord) -> ResumeResponse:
    try:
        return ResumeResponse(
            exists=True,
            content=ResumeContent.model_validate(record.content),
            style_config=ResumeStyleConfig.model_validate(record.style_config),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
    except Exception:
        logger.error("已保存简历 DTO 校验失败")
        raise ResumeStorageUnavailableError() from None


def _read_photo_id(content: dict[str, Any]) -> str | None:
    basic_info = content.get("basic_info")
    if not isinstance(basic_info, dict):
        return None
    photo_id = basic_info.get("photo_id")
    return photo_id if isinstance(photo_id, str) else None
