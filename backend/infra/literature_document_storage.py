"""文献 PDF 私有 OSS 存储适配器，不复用图片附件的格式校验。"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from infra.settings import AppSettings


logger = logging.getLogger(__name__)


class LiteratureStorageError(RuntimeError):
    """文献对象读写失败时使用的安全存储异常。"""


class LiteratureStorageNotConfiguredError(LiteratureStorageError):
    """文献 PDF 需要 OSS，但运行环境没有配置 OSS 时抛出。"""


class AliyunOSSLiteratureStorage:
    """将原始文献 PDF 写入私有 OSS，并按可信主体隔离对象键。"""

    def __init__(self, settings: AppSettings) -> None:
        """基于项目 OSS 配置创建文献对象 Bucket 客户端。"""
        if not settings.aliyun_oss_configured:
            raise LiteratureStorageNotConfiguredError("文献文件存储尚未配置阿里云 OSS")
        import oss2

        auth = oss2.Auth(
            settings.aliyun_oss_access_key_id.get_secret_value(),
            settings.aliyun_oss_access_key_secret.get_secret_value(),
        )
        self._bucket = oss2.Bucket(
            auth,
            settings.aliyun_oss_endpoint.rstrip("/"),
            settings.aliyun_oss_bucket,
        )
        self._prefix = settings.aliyun_oss_object_prefix.strip("/")

    def save_pdf(
        self,
        principal_id: str,
        document_id: str,
        file_name: str,
        pdf_bytes: bytes,
    ) -> str:
        """保存 PDF 原件并返回不含公开凭据的对象键。"""
        del file_name  # 原始文件名保存在数据库，避免写入受 Latin-1 限制的 HTTP 头。
        object_key = self._object_key(principal_id, document_id)
        try:
            self._bucket.put_object(
                object_key,
                pdf_bytes,
                headers={
                    "Content-Type": "application/pdf",
                    "Content-Disposition": "attachment",
                    "x-oss-meta-owner-hash": _owner_hash(principal_id),
                },
            )
            return object_key
        except Exception as error:
            logger.warning("文献 PDF 上传 OSS 失败 error_type=%s", type(error).__name__)
            raise LiteratureStorageError("文献文件保存失败") from error

    def read_pdf(self, principal_id: str, object_key: str) -> bytes:
        """校验对象键属于当前可信主体后读取 PDF 原件。"""
        if object_key != self._object_key_from_hash(
            _owner_hash(principal_id),
            object_key.rsplit("/", 1)[-1].removesuffix(".pdf"),
        ):
            raise LiteratureStorageError("文献文件不存在")
        try:
            response = self._bucket.get_object(object_key)
            return response.read()
        except Exception as error:
            logger.warning("文献 PDF 读取 OSS 失败 error_type=%s", type(error).__name__)
            raise LiteratureStorageError("文献文件暂时无法读取") from error

    def delete_pdf(self, principal_id: str, object_key: str) -> None:
        """仅删除当前可信主体文献目录内的 OSS 对象。"""
        if not object_key.startswith(self._owner_prefix(principal_id)):
            raise LiteratureStorageError("文献文件不存在")
        try:
            self._bucket.delete_object(object_key)
        except Exception as error:
            logger.warning("文献 PDF 删除 OSS 失败 error_type=%s", type(error).__name__)
            raise LiteratureStorageError("文献文件删除失败") from error

    def _object_key(self, principal_id: str, document_id: str) -> str:
        """构造包含主体散列和文献 ID 的稳定私有对象键。"""
        owner_hash = _owner_hash(principal_id)
        return self._object_key_from_hash(owner_hash, document_id)

    def _object_key_from_hash(self, owner_hash: str, document_id: str) -> str:
        """将文献 PDF 保存在独立的 literature 前缀中。"""
        prefix = f"{self._prefix}/literature" if self._prefix else "literature"
        return f"{prefix}/{owner_hash}/{document_id}.pdf"

    def _owner_prefix(self, principal_id: str) -> str:
        """返回指定可信主体唯一拥有的文献对象目录。"""
        prefix = f"{self._prefix}/literature" if self._prefix else "literature"
        return f"{prefix}/{_owner_hash(principal_id)}/"


class UnavailableLiteratureStorage:
    """OSS 未配置时保留 Web 文献导入能力，并明确拒绝 PDF 原件操作。"""

    def __init__(self) -> None:
        """创建未配置状态的文献存储适配器。"""

    @staticmethod
    def _raise_not_configured() -> None:
        """拒绝依赖 OSS 的 PDF 原件读写。"""
        raise LiteratureStorageNotConfiguredError("文献 PDF 存储尚未配置阿里云 OSS")

    def save_pdf(self, *_: object, **__: object) -> str:
        """拒绝保存未配置 OSS 的 PDF 文件。"""
        self._raise_not_configured()

    def read_pdf(self, *_: object, **__: object) -> bytes:
        """拒绝读取未配置 OSS 的 PDF 文件。"""
        self._raise_not_configured()

    def delete_pdf(self, *_: object, **__: object) -> None:
        """拒绝删除未配置 OSS 的 PDF 文件。"""
        self._raise_not_configured()


def _owner_hash(principal_id: str) -> str:
    """以不可逆短摘要组织对象目录，避免在 OSS 键中泄露主体标识。"""
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:24]

