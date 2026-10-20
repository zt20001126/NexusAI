"""简历助手 API 的固定主体、JSON 契约和二进制响应测试。"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.resume_owner import RESUME_OWNER_PRINCIPAL_ID
from app.schemas.resume import (
    ResumeContent,
    ResumePhotoUploadResponse,
    ResumeResponse,
    ResumeSaveRequest,
    ResumeStyleConfig,
)
from bootstrap.application import create_app
from infra.settings import AppSettings

TEST_PNG = b"\x89PNG\r\n\x1a\nresume-test-image"
TEST_PDF = b"%PDF-1.7 resume-test"


class FakeResumeService:
    """隔离 HTTP 契约，不连接 PostgreSQL、OSS 或 Chromium。"""

    def __init__(self) -> None:
        self.principals: list[str] = []
        self.saved_payload: ResumeSaveRequest | None = None
        self.photo_bytes: bytes | None = None
        self.deleted_photo_ids: list[str] = []

    def get_resume(self, principal_id: str) -> ResumeResponse:
        self.principals.append(principal_id)
        if self.saved_payload is None:
            return ResumeResponse(
                exists=False,
                content=ResumeContent(),
                style_config=ResumeStyleConfig(),
            )
        return _saved_response(self.saved_payload)

    def save_resume(
        self, principal_id: str, payload: ResumeSaveRequest
    ) -> ResumeResponse:
        self.principals.append(principal_id)
        self.saved_payload = payload
        return _saved_response(payload)

    def upload_photo(self, principal_id: str, data: bytes) -> ResumePhotoUploadResponse:
        self.principals.append(principal_id)
        self.photo_bytes = data
        return ResumePhotoUploadResponse(
            photo_id="a" * 32,
            mime_type="image/png",
            file_size=len(data),
        )

    def get_saved_photo(self, principal_id: str) -> tuple[bytes, str]:
        self.principals.append(principal_id)
        return TEST_PNG, "image/png"

    def delete_staged_photo(self, principal_id: str, photo_id: str) -> None:
        self.principals.append(principal_id)
        self.deleted_photo_ids.append(photo_id)

    def export_pdf(self, principal_id: str) -> bytes:
        self.principals.append(principal_id)
        return TEST_PDF


@pytest.fixture
def client() -> Any:
    service = FakeResumeService()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.resume_service = service
        yield

    application = create_app(AppSettings(_env_file=None), lifespan=lifespan)
    with TestClient(application) as test_client:
        test_client.app.state.fake_resume_service = service
        yield test_client


def test_get_returns_defaults_without_external_identity(client: TestClient) -> None:
    response = client.get("/api/resume")

    assert response.status_code == 200
    assert response.json()["data"]["exists"] is False
    assert response.json()["data"]["content"]["skills"] == {
        "type": "doc",
        "content": [{"type": "paragraph", "content": []}],
    }
    assert response.headers["cache-control"] == "private, no-store"
    assert client.app.state.fake_resume_service.principals == [RESUME_OWNER_PRINCIPAL_ID]


def test_put_persists_rich_skills_and_rejects_owner_fields(
    client: TestClient,
) -> None:
    response = client.put("/api/resume", json=_valid_payload())

    assert response.status_code == 200
    assert response.json()["data"]["content"]["skills"] == {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Python", "marks": None}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "FastAPI", "marks": None}]},
        ],
    }
    assert client.app.state.fake_resume_service.saved_payload is not None

    invalid_payload = _valid_payload()
    invalid_payload["owner_id"] = "another-owner"
    rejected = client.put("/api/resume", json=invalid_payload)
    assert rejected.status_code == 422
    assert rejected.json()["code"] == "INVALID_RESUME_DATA"


def test_put_rejects_legacy_skill_array(client: TestClient) -> None:
    payload = _valid_payload()
    payload["content"]["skills"] = ["Python", "FastAPI"]

    response = client.put("/api/resume", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RESUME_DATA"


def test_put_persists_manual_age_and_work_experience_without_birth_month(
    client: TestClient,
) -> None:
    payload = _valid_payload()
    payload["content"]["basic_info"].update(
        {"age": 29, "work_experience_years": 5}
    )

    response = client.put("/api/resume", json=payload)

    assert response.status_code == 200
    basic_info = response.json()["data"]["content"]["basic_info"]
    assert basic_info["age"] == 29
    assert basic_info["work_experience_years"] == 5
    assert "birth_month" not in basic_info


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("age", -1),
        ("age", 121),
        ("age", "29"),
        ("work_experience_years", -1),
        ("work_experience_years", 81),
        ("work_experience_years", 2.5),
    ],
)
def test_manual_year_fields_reject_values_outside_integer_ranges(
    client: TestClient,
    field: str,
    value: object,
) -> None:
    payload = _valid_payload()
    payload["content"]["basic_info"][field] = value

    response = client.put("/api/resume", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RESUME_DATA"


def test_put_rejects_removed_birth_month_field(client: TestClient) -> None:
    payload = _valid_payload()
    payload["content"]["basic_info"]["birth_month"] = "1996-08"

    response = client.put("/api/resume", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RESUME_DATA"


def test_put_rejects_non_document_skill_values(client: TestClient) -> None:
    payload = _valid_payload()
    payload["content"]["skills"] = [{"type": "paragraph", "text": "Python"}]

    response = client.put("/api/resume", json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "INVALID_RESUME_DATA"


def test_resume_json_body_limit_is_enforced_before_validation(client: TestClient) -> None:
    oversized = b"{" + b" " * (256 * 1024) + b"}"

    response = client.put(
        "/api/resume",
        content=oversized,
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json()["code"] == "REQUEST_TOO_LARGE"
    assert response.headers["cache-control"] == "private, no-store"


def test_photo_upload_delete_and_binary_responses_use_fixed_owner(
    client: TestClient,
) -> None:
    uploaded = client.post(
        "/api/resume/photo",
        files={"file": ("photo.png", TEST_PNG, "application/octet-stream")},
    )
    assert uploaded.status_code == 200
    assert uploaded.json()["data"] == {
        "photo_id": "a" * 32,
        "mime_type": "image/png",
        "file_size": len(TEST_PNG),
    }

    photo = client.get("/api/resume/photo")
    assert photo.content == TEST_PNG
    assert photo.headers["content-type"] == "image/png"
    assert photo.headers["x-content-type-options"] == "nosniff"
    assert photo.headers["cache-control"] == "private, no-store"

    deleted = client.delete("/api/resume/photo", params={"photo_id": "a" * 32})
    assert deleted.status_code == 200
    assert client.app.state.fake_resume_service.deleted_photo_ids == ["a" * 32]

    invalid_id = client.delete("/api/resume/photo", params={"photo_id": "invalid"})
    assert invalid_id.status_code == 400
    assert invalid_id.json()["code"] == "INVALID_RESUME_PHOTO_ID"

    pdf = client.get("/api/resume/export/pdf")
    assert pdf.content == TEST_PDF
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.headers["content-disposition"] == 'attachment; filename="resume.pdf"'
    assert pdf.headers["cache-control"] == "private, no-store"

    assert set(client.app.state.fake_resume_service.principals) == {
        RESUME_OWNER_PRINCIPAL_ID
    }


def _valid_payload() -> dict[str, Any]:
    content = ResumeContent().model_dump(mode="json")
    content["basic_info"].update(
        {
            "name": "张三",
            "phone": "13800000000",
            "email": "zhangsan@example.com",
        }
    )
    content["skills"] = {
        "type": "doc",
        "content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Python"}]},
            {"type": "paragraph", "content": [{"type": "text", "text": "FastAPI"}]},
        ],
    }
    return {
        "content": content,
        "style_config": ResumeStyleConfig().model_dump(mode="json"),
    }


def _saved_response(payload: ResumeSaveRequest) -> ResumeResponse:
    now = datetime.now(timezone.utc)
    return ResumeResponse(
        exists=True,
        content=payload.content,
        style_config=payload.style_config,
        created_at=now,
        updated_at=now,
    )
