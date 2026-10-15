"""阿里云 OSS 适配器测试；使用内存 Bucket，不访问云端。"""

from __future__ import annotations

from dataclasses import dataclass

import oss2
import pytest

from agent.errors import AttachmentAccessDeniedError
from infra.aliyun_oss import AliyunOSSImageStorage
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator

TEST_PNG = b"\x89PNG\r\n\x1a\noss-adapter-test"


@dataclass
class FakeObjectResponse:
    """实现 OSS 对象响应使用到的最小接口。"""

    data: bytes
    headers: dict[str, str]
    closed: bool = False

    def read(self, amount: int = -1) -> bytes:
        return self.data[:amount]

    def close(self) -> None:
        self.closed = True


@dataclass
class FakeObjectMetadata:
    """实现 OSS HEAD 元数据响应。"""

    headers: dict[str, str]


class FakeBucket:
    """保留 OSS 对象，并模拟 objectMeta 与普通 HEAD 的响应差异。"""

    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str]]] = {}

    def put_object(
        self,
        key: str,
        data: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.objects[key] = (data, dict(headers or {}))

    def get_object_meta(self, key: str) -> FakeObjectMetadata:
        data, _ = self.objects[key]
        return FakeObjectMetadata(
            {
                "ETag": '"fake-etag"',
                "Content-Length": str(len(data)),
            }
        )

    def head_object(self, key: str) -> FakeObjectMetadata:
        data, headers = self.objects[key]
        return FakeObjectMetadata(
            {
                **headers,
                "Content-Length": str(len(data)),
            }
        )

    def get_object(self, key: str) -> FakeObjectResponse:
        data, headers = self.objects[key]
        return FakeObjectResponse(
            data,
            {
                **headers,
                "Content-Length": str(len(data)),
            },
        )

    def copy_object(self, bucket_name: str, source_key: str, target_key: str) -> None:
        del bucket_name
        self.objects[target_key] = self.objects[source_key]

    def delete_object(self, key: str) -> None:
        self.objects.pop(key, None)


@pytest.fixture
def oss_storage(monkeypatch: pytest.MonkeyPatch) -> tuple[AliyunOSSImageStorage, FakeBucket]:
    bucket = FakeBucket()
    monkeypatch.setattr(oss2, "Bucket", lambda *_: bucket)
    settings = AppSettings(
        aliyun_oss_access_key_id="test-access-key",
        aliyun_oss_access_key_secret="test-access-secret",
        aliyun_oss_bucket="private-test-bucket",
        aliyun_oss_object_prefix="nexus-test",
        _env_file=None,
    )
    return AliyunOSSImageStorage(settings, SnowflakeIdGenerator(worker_id=7)), bucket


def test_reference_image_moves_to_private_prefix_and_loads_for_owner(
    oss_storage: tuple[AliyunOSSImageStorage, FakeBucket],
) -> None:
    storage, bucket = oss_storage

    attachment = storage.save("trusted-user", "product.png", "image/png", TEST_PNG)
    storage.validate_staged([attachment.attachment_id], "trusted-user")
    storage.bind_to_message(
        [attachment.attachment_id],
        "trusted-user",
        "123456",
        "234567",
    )

    loaded = storage.list_for_generation(
        [attachment.attachment_id],
        "trusted-user",
        "123456",
    )[0]

    assert attachment.attachment_id.isdigit()
    assert loaded.image_data == TEST_PNG
    assert loaded.file_name == "product.png"
    assert all("trusted-user" not in key for key in bucket.objects)
    assert all("staged/" not in key for key in bucket.objects)


def test_generated_image_is_saved_and_read_only_from_owners_prefix(
    oss_storage: tuple[AliyunOSSImageStorage, FakeBucket],
) -> None:
    storage, _ = oss_storage
    stored = storage.save_result("trusted-user", "345678", TEST_PNG, "image/png")

    assert storage.read_result(stored.object_key, "trusted-user") == (
        TEST_PNG,
        "image/png",
    )
    with pytest.raises(AttachmentAccessDeniedError):
        storage.read_result(stored.object_key, "another-user")
    with pytest.raises(AttachmentAccessDeniedError):
        storage.read_result("nexus-test/generated/other-user/image.png", "trusted-user")


def test_oss_adapter_rejects_content_without_matching_image_signature(
    oss_storage: tuple[AliyunOSSImageStorage, FakeBucket],
) -> None:
    storage, _ = oss_storage

    with pytest.raises(AttachmentAccessDeniedError):
        storage.save("trusted-user", "fake.png", "image/png", b"not an image")
