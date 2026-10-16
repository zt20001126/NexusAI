"""文献 PDF OSS 对象存储回归测试。"""

from __future__ import annotations

import oss2
import pytest

from infra.literature_document_storage import (
    AliyunOSSLiteratureStorage,
    LiteratureStorageError,
)
from infra.settings import AppSettings


class HttpHeaderBucket:
    """模拟 OSS SDK 将请求头编码为 HTTP 字节时的约束。"""

    def __init__(self) -> None:
        self.saved_object: tuple[str, bytes] | None = None

    def put_object(
        self,
        key: str,
        data: bytes,
        headers: dict[str, str] | None = None,
    ) -> None:
        for name, value in (headers or {}).items():
            name.encode("ascii")
            value.encode("latin-1")
        self.saved_object = (key, data)


def test_chinese_pdf_file_name_can_be_saved_to_oss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """中文文件名不应进入无法编码的 HTTP 元数据头并阻断 PDF 上传。"""
    bucket = HttpHeaderBucket()
    monkeypatch.setattr(oss2, "Bucket", lambda *_: bucket)
    settings = AppSettings(
        aliyun_oss_access_key_id="test-access-key",
        aliyun_oss_access_key_secret="test-access-secret",
        aliyun_oss_bucket="private-test-bucket",
        _env_file=None,
    )
    storage = AliyunOSSLiteratureStorage(settings)
    pdf_bytes = b"%PDF-1.7 test"

    try:
        object_key = storage.save_pdf(
            "trusted-user", "123456", "中文文献.pdf", pdf_bytes
        )
    except LiteratureStorageError as error:
        pytest.fail(f"中文文件名导致 OSS PDF 上传失败: {error.__cause__!r}")

    assert object_key.isascii()
    assert bucket.saved_object == (object_key, pdf_bytes)
