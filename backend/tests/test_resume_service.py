"""简历用例服务的保存顺序、照片补偿和导出数据来源测试。"""

from datetime import datetime, timezone
from typing import Any

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.crud.resume import ResumeRecord
from app.exceptions.resume import ResumeStorageUnavailableError
from app.schemas.resume import ResumeContent, ResumeSaveRequest, ResumeStyleConfig
from app.service.resume import ResumeApplicationService


class FakeResumeRepository:
    def __init__(
        self,
        record: ResumeRecord | None = None,
        *,
        fail_upsert: bool = False,
        event_log: list[str] | None = None,
    ):
        self.record = record
        self.fail_upsert = fail_upsert
        self.events = event_log if event_log is not None else []

    def get(self, principal_id: str) -> ResumeRecord | None:
        self.events.append(f"get:{principal_id}")
        return self.record

    def upsert(
        self,
        principal_id: str,
        *,
        content: dict[str, Any],
        style_config: dict[str, Any],
    ) -> ResumeRecord:
        self.events.append(f"upsert:{principal_id}")
        if self.fail_upsert:
            raise SQLAlchemyError("database unavailable")
        now = datetime.now(timezone.utc)
        self.record = ResumeRecord(content, style_config, now, now)
        return self.record


class FakeResumePhotoStorage:
    def __init__(self, event_log: list[str] | None = None) -> None:
        self.events = event_log if event_log is not None else []

    def save_staged(self, principal_id: str, photo_id: str, data: bytes) -> str:
        self.events.append(f"stage:{photo_id}")
        return photo_id

    def promote_staged(self, principal_id: str, photo_id: str) -> None:
        self.events.append(f"promote:{photo_id}")

    def read_final(self, principal_id: str, photo_id: str) -> tuple[bytes, str]:
        self.events.append(f"read:{photo_id}")
        return b"\x89PNG\r\n\x1a\nimage", "image/png"

    def delete_staged(self, principal_id: str, photo_id: str) -> None:
        self.events.append(f"delete-staged:{photo_id}")

    def delete_final(self, principal_id: str, photo_id: str) -> None:
        self.events.append(f"delete-final:{photo_id}")

    def cleanup_unreferenced_final(
        self, principal_id: str, referenced_photo_id: str | None, *, min_age_seconds: int
    ) -> None:
        self.events.append(f"cleanup:{referenced_photo_id}")


class FakeResumePdfRenderer:
    def __init__(self) -> None:
        self.html: str | None = None

    def render(self, html_document: str) -> bytes:
        self.html = html_document
        return b"saved-resume-pdf"


def test_get_empty_resume_does_not_write_repository() -> None:
    repository = FakeResumeRepository()
    storage = FakeResumePhotoStorage()
    service = _service(repository, storage)

    response = service.get_resume("fixed-owner")

    assert response.exists is False
    assert response.content.skills == []
    assert repository.events == ["get:fixed-owner"]
    assert storage.events == ["cleanup:None"]


def test_get_migrated_resume_defaults_manual_profile_values_to_empty() -> None:
    migrated_content = {
        "basic_info": {
            "name": "Existing Name",
            "phone": "13800000000",
            "email": "existing@example.com",
            "intended_position": "Engineer",
            "photo_id": None,
        },
        "educations": [],
        "skills": [],
        "works": [],
        "projects": [],
    }
    now = datetime.now(timezone.utc)
    repository = FakeResumeRepository(
        ResumeRecord(
            migrated_content,
            ResumeStyleConfig().model_dump(mode="json"),
            now,
            now,
        )
    )
    service = _service(repository, FakeResumePhotoStorage())

    response = service.get_resume("fixed-owner")

    assert response.content.basic_info.age is None
    assert response.content.basic_info.work_experience_years is None


def test_photo_is_promoted_before_database_switch_and_old_photo_deleted_after() -> None:
    old_photo_id = "1" * 32
    new_photo_id = "2" * 32
    existing = _record(photo_id=old_photo_id)
    timeline: list[str] = []
    repository = FakeResumeRepository(existing, event_log=timeline)
    storage = FakeResumePhotoStorage(timeline)
    service = _service(repository, storage)

    response = service.save_resume("fixed-owner", _payload(photo_id=new_photo_id))

    assert response.exists is True
    assert response.content.basic_info.photo_id == new_photo_id
    assert timeline.index(f"promote:{new_photo_id}") < timeline.index("upsert:fixed-owner")
    assert timeline.index("upsert:fixed-owner") < timeline.index(
        f"delete-final:{old_photo_id}"
    )
    assert timeline.index(f"delete-final:{old_photo_id}") < timeline.index(
        f"delete-staged:{new_photo_id}"
    )


def test_database_failure_removes_promoted_object_and_keeps_staging_for_retry() -> None:
    new_photo_id = "3" * 32
    repository = FakeResumeRepository(_record(photo_id=None), fail_upsert=True)
    storage = FakeResumePhotoStorage()
    service = _service(repository, storage)

    with pytest.raises(ResumeStorageUnavailableError):
        service.save_resume("fixed-owner", _payload(photo_id=new_photo_id))

    assert storage.events == [f"promote:{new_photo_id}", f"delete-final:{new_photo_id}"]
    assert f"delete-staged:{new_photo_id}" not in storage.events


def test_pdf_export_uses_saved_content_and_renderer_output() -> None:
    repository = FakeResumeRepository(_record(photo_id=None))
    storage = FakeResumePhotoStorage()
    renderer = FakeResumePdfRenderer()
    service = _service(repository, storage, renderer)

    pdf = service.export_pdf("fixed-owner")

    assert pdf == b"saved-resume-pdf"
    assert renderer.html is not None
    assert "Saved Name" in renderer.html
    assert "unsaved draft" not in renderer.html


def _service(
    repository: FakeResumeRepository,
    storage: FakeResumePhotoStorage,
    renderer: FakeResumePdfRenderer | None = None,
) -> ResumeApplicationService:
    return ResumeApplicationService(
        repository=repository,  # type: ignore[arg-type]
        photo_storage=storage,
        pdf_renderer=renderer or FakeResumePdfRenderer(),
    )


def _payload(*, photo_id: str | None) -> ResumeSaveRequest:
    content = ResumeContent.model_validate(
        {
            "basic_info": {
                "name": "Saved Name",
                "phone": "13800000000",
                "email": "saved@example.com",
                "photo_id": photo_id,
            },
            "skills": ["Python", "FastAPI"],
        }
    )
    return ResumeSaveRequest(content=content, style_config=ResumeStyleConfig())


def _record(*, photo_id: str | None) -> ResumeRecord:
    request = _payload(photo_id=photo_id)
    now = datetime.now(timezone.utc)
    return ResumeRecord(
        request.content.model_dump(mode="json", exclude_none=True),
        request.style_config.model_dump(mode="json"),
        now,
        now,
    )
