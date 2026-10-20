"""简历照片 OSS 适配器的签名、主体隔离及孤儿回收测试。"""

from dataclasses import dataclass
from io import BytesIO
import time
from typing import Any

import pytest

from infra.resume_photo_storage import (
    AliyunOSSResumePhotoStorage,
    ResumePhotoInvalidContentError,
    ResumePhotoObjectNotFoundError,
)

PNG = b"\x89PNG\r\n\x1a\nimage-bytes"
JPEG = b"\xff\xd8\xffimage-bytes"


class MissingObjectError(RuntimeError):
    status = 404


@dataclass
class FakeObject:
    data: bytes
    headers: dict[str, str]
    last_modified: float


class FakeGetObject(BytesIO):
    pass


class FakeBucket:
    def __init__(self) -> None:
        self.objects: dict[str, FakeObject] = {}

    def put_object(self, key: str, data: bytes, *, headers: dict[str, str]) -> None:
        self.objects[key] = FakeObject(data, headers, time.time())

    def head_object(self, key: str) -> Any:
        if key not in self.objects:
            raise MissingObjectError(key)
        return type("Head", (), {"headers": self.objects[key].headers})()

    def copy_object(self, bucket: str, source: str, target: str) -> None:
        del bucket
        item = self.objects[source]
        self.objects[target] = FakeObject(item.data, dict(item.headers), time.time())

    def get_object(self, key: str) -> FakeGetObject:
        if key not in self.objects:
            raise MissingObjectError(key)
        return FakeGetObject(self.objects[key].data)

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)

    def list_objects(self, *, prefix: str, marker: str | None, max_keys: int) -> Any:
        del marker, max_keys
        rows = [
            type("ListedObject", (), {"key": key, "last_modified": item.last_modified})()
            for key, item in self.objects.items()
            if key.startswith(prefix)
        ]
        return type(
            "ListResult",
            (),
            {"object_list": rows, "is_truncated": False, "next_marker": None},
        )()


@pytest.fixture
def storage() -> AliyunOSSResumePhotoStorage:
    result = object.__new__(AliyunOSSResumePhotoStorage)
    result._bucket = FakeBucket()
    result._bucket_name = "private-resume-bucket"
    result._prefix = "nexus"
    result._max_bytes = 5 * 1024 * 1024
    return result


@pytest.mark.parametrize(("data", "mime_type"), [(PNG, "image/png"), (JPEG, "image/jpeg")])
def test_staging_promotion_and_read_verify_owner_and_signature(
    storage: AliyunOSSResumePhotoStorage, data: bytes, mime_type: str
) -> None:
    photo_id = "a" * 32

    assert storage.save_staged("owner-1", photo_id, data) == photo_id
    storage.promote_staged("owner-1", photo_id)
    saved, detected_mime_type = storage.read_final("owner-1", photo_id)

    assert saved == data
    assert detected_mime_type == mime_type
    with pytest.raises(ResumePhotoObjectNotFoundError):
        storage.read_final("owner-2", photo_id)


@pytest.mark.parametrize("data", [b"not-an-image", b""])
def test_upload_rejects_invalid_image_signature(
    storage: AliyunOSSResumePhotoStorage, data: bytes
) -> None:
    with pytest.raises(ResumePhotoInvalidContentError):
        storage.save_staged("owner-1", "b" * 32, data)


def test_upload_enforces_size_and_orphan_cleanup_preserves_reference(
    storage: AliyunOSSResumePhotoStorage,
) -> None:
    with pytest.raises(ResumePhotoInvalidContentError):
        storage.save_staged("owner-1", "c" * 32, PNG + b"x" * (5 * 1024 * 1024))

    retained_id = "d" * 32
    orphan_id = "e" * 32
    storage.save_staged("owner-1", retained_id, PNG)
    storage.promote_staged("owner-1", retained_id)
    storage.save_staged("owner-1", orphan_id, PNG)
    storage.promote_staged("owner-1", orphan_id)
    bucket = storage._bucket
    for key, item in bucket.objects.items():
        if "/final/" in key and orphan_id in key:
            item.last_modified = time.time() - 90_000

    storage.cleanup_unreferenced_final(
        "owner-1", retained_id, min_age_seconds=86_400
    )

    assert storage.read_final("owner-1", retained_id)[0] == PNG
    with pytest.raises(ResumePhotoObjectNotFoundError):
        storage.read_final("owner-1", orphan_id)
