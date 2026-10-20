"""把简历照片保存在私有 OSS，并按固定主体隔离 staging/final 对象。"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from typing import Any

from infra.settings import AppSettings

logger = logging.getLogger(__name__)
_PHOTO_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_MIME_BY_EXTENSION = {"png": "image/png", "jpg": "image/jpeg"}
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class ResumePhotoStorageError(RuntimeError):
    """OSS 简历照片读写失败时使用的安全基础错误。"""


class ResumePhotoStorageNotConfiguredError(ResumePhotoStorageError):
    """OSS 配置缺失。"""


class ResumePhotoObjectNotFoundError(ResumePhotoStorageError):
    """当前主体没有对应暂存或最终照片对象。"""


class ResumePhotoInvalidContentError(ValueError):
    """文件签名不是有效 PNG/JPEG 或超过大小上限。"""


class ResumePhotoTooLargeContentError(ResumePhotoInvalidContentError):
    """照片超过当前服务允许的上传大小。"""


class AliyunOSSResumePhotoStorage:
    """使用 OSS 私有对象保存照片；客户端只接触随机 photo_id。"""

    def __init__(self, settings: AppSettings) -> None:
        if not settings.aliyun_oss_configured:
            raise ResumePhotoStorageNotConfiguredError("简历照片存储未配置")
        import oss2

        self._oss2: Any = oss2
        auth = oss2.Auth(
            settings.aliyun_oss_access_key_id.get_secret_value(),
            settings.aliyun_oss_access_key_secret.get_secret_value(),
        )
        self._bucket = oss2.Bucket(
            auth,
            settings.aliyun_oss_endpoint.rstrip("/"),
            settings.aliyun_oss_bucket,
        )
        self._bucket_name = settings.aliyun_oss_bucket
        self._prefix = settings.aliyun_oss_object_prefix.strip("/")
        self._max_bytes = min(settings.image_upload_max_bytes, 5 * 1024 * 1024)

    def save_staged(self, principal_id: str, photo_id: str, data: bytes) -> str:
        """签名校验后保存一个不可公开访问的 staging 对象。"""
        self._validate_photo_id(photo_id)
        if not data:
            raise ResumePhotoInvalidContentError("照片为空")
        if len(data) > self._max_bytes:
            raise ResumePhotoTooLargeContentError("照片超过允许大小")
        mime_type = self._detect_mime_type(data)
        owner_hash = _owner_hash(principal_id)
        object_key = self._object_key("staged", owner_hash, photo_id, mime_type)
        try:
            self._bucket.put_object(
                object_key,
                data,
                headers={
                    "Content-Type": mime_type,
                    "x-oss-meta-owner-hash": owner_hash,
                },
            )
            return photo_id
        except Exception as error:
            self._raise_storage_error("save_staged", error)

    def promote_staged(self, principal_id: str, photo_id: str) -> None:
        """校验 staging 归属并复制到 photo_id 对应的最终对象键。"""
        owner_hash = _owner_hash(principal_id)
        source_key, extension, mime_type = self._find_object(
            prefix="staged", owner_hash=owner_hash, photo_id=photo_id
        )
        target_key = self._object_key("final", owner_hash, photo_id, mime_type)
        try:
            self._bucket.copy_object(self._bucket_name, source_key, target_key)
        except Exception as error:
            self._raise_storage_error("promote_staged", error)
        del extension

    def read_final(self, principal_id: str, photo_id: str) -> tuple[bytes, str]:
        """验证最终对象归属、签名和字节上限后返回照片。"""
        owner_hash = _owner_hash(principal_id)
        object_key, _, mime_type = self._find_object(
            prefix="final", owner_hash=owner_hash, photo_id=photo_id
        )
        try:
            response = self._bucket.get_object(object_key)
            data = response.read(self._max_bytes + 1)
        except Exception as error:
            self._raise_storage_error("read_final", error)
        if len(data) > self._max_bytes:
            raise ResumePhotoStorageError("已保存照片超过读取上限")
        if self._detect_mime_type(data) != mime_type:
            raise ResumePhotoStorageError("已保存照片签名与对象类型不一致")
        return data, mime_type

    def delete_staged(self, principal_id: str, photo_id: str) -> None:
        """删除当前主体名下的 staging 对象；对象已过期时保持幂等。"""
        self._delete_object_if_owned("staged", principal_id, photo_id)

    def delete_final(self, principal_id: str, photo_id: str) -> None:
        """删除当前主体名下指定 photo_id 的最终对象。"""
        self._delete_object_if_owned("final", principal_id, photo_id)

    def cleanup_unreferenced_final(
        self,
        principal_id: str,
        referenced_photo_id: str | None,
        *,
        min_age_seconds: int = 86_400,
    ) -> None:
        """回收主体目录中未被当前简历引用且超过宽限期的孤儿照片。"""
        owner_hash = _owner_hash(principal_id)
        prefix = self._owner_prefix(owner_hash, "final")
        referenced_keys = {
            self._object_key("final", owner_hash, referenced_photo_id, mime_type)
            for mime_type in _MIME_BY_EXTENSION.values()
        } if referenced_photo_id else set()
        cutoff = time.time() - min_age_seconds
        marker: str | None = None
        try:
            while True:
                result = self._bucket.list_objects(
                    prefix=prefix,
                    marker=marker,
                    max_keys=100,
                )
                for item in result.object_list:
                    if item.key in referenced_keys or not _valid_final_key(item.key, prefix):
                        continue
                    if float(item.last_modified) >= cutoff:
                        continue
                    self._verify_owner(item.key, owner_hash)
                    self._bucket.delete_object(item.key)
                if not result.is_truncated:
                    break
                marker = result.next_marker
                if not marker:
                    break
        except Exception as error:
            # 回收是尽力操作，OSS 暂时故障不阻断简历读写。
            logger.warning(
                "简历孤儿照片回收失败 error_type=%s", type(error).__name__
            )

    def _delete_object_if_owned(
        self, prefix: str, principal_id: str, photo_id: str
    ) -> None:
        self._validate_photo_id(photo_id)
        owner_hash = _owner_hash(principal_id)
        found = False
        for mime_type in _MIME_BY_EXTENSION.values():
            key = self._object_key(prefix, owner_hash, photo_id, mime_type)
            try:
                self._verify_owner(key, owner_hash)
            except ResumePhotoObjectNotFoundError:
                continue
            found = True
            try:
                self._bucket.delete_object(key)
            except Exception as error:
                self._raise_storage_error("delete_photo", error)
        if prefix == "staged" and not found:
            # OSS 生命周期可能已删除 staging；取消操作可以安全重试。
            return
        if prefix == "final" and not found:
            raise ResumePhotoObjectNotFoundError("简历照片不存在")

    def _find_object(
        self,
        *,
        prefix: str,
        owner_hash: str,
        photo_id: str,
    ) -> tuple[str, str, str]:
        self._validate_photo_id(photo_id)
        for extension, mime_type in _MIME_BY_EXTENSION.items():
            key = self._object_key(prefix, owner_hash, photo_id, mime_type)
            try:
                self._verify_owner(key, owner_hash)
                return key, extension, mime_type
            except ResumePhotoObjectNotFoundError:
                continue
        raise ResumePhotoObjectNotFoundError("简历照片不存在")

    def _verify_owner(self, object_key: str, owner_hash: str) -> None:
        try:
            metadata = self._bucket.head_object(object_key)
        except Exception as error:
            if getattr(error, "status", None) == 404:
                raise ResumePhotoObjectNotFoundError("简历照片不存在") from None
            self._raise_storage_error("head_photo", error)
        headers = {key.lower(): value for key, value in metadata.headers.items()}
        if headers.get("x-oss-meta-owner-hash") != owner_hash:
            raise ResumePhotoObjectNotFoundError("简历照片不存在")

    def _object_key(
        self, prefix: str, owner_hash: str, photo_id: str, mime_type: str
    ) -> str:
        extension = "png" if mime_type == "image/png" else "jpg"
        return f"{self._owner_prefix(owner_hash, prefix)}{photo_id}.{extension}"

    def _owner_prefix(self, owner_hash: str, prefix: str) -> str:
        base = f"{self._prefix}/resume" if self._prefix else "resume"
        return f"{base}/{owner_hash}/{prefix}/"

    def _detect_mime_type(self, data: bytes) -> str:
        if data.startswith(_PNG_SIGNATURE):
            return "image/png"
        if len(data) >= 3 and data[:3] == b"\xff\xd8\xff":
            return "image/jpeg"
        raise ResumePhotoInvalidContentError("文件签名不是 PNG 或 JPEG")

    def _validate_photo_id(self, photo_id: str) -> None:
        if not _PHOTO_ID_PATTERN.fullmatch(photo_id):
            raise ResumePhotoObjectNotFoundError("简历照片不存在")

    @staticmethod
    def _raise_storage_error(operation: str, error: Exception) -> None:
        logger.warning(
            "简历照片 OSS 操作失败 operation=%s error_type=%s",
            operation,
            type(error).__name__,
        )
        raise ResumePhotoStorageError("简历照片存储操作失败") from error


class UnavailableResumePhotoStorage:
    """OSS 未配置时仍允许编辑无照片简历。"""

    @staticmethod
    def _raise_not_configured() -> None:
        raise ResumePhotoStorageNotConfiguredError("简历照片存储未配置")

    def save_staged(self, *_: object, **__: object) -> str:
        self._raise_not_configured()

    def promote_staged(self, *_: object, **__: object) -> None:
        self._raise_not_configured()

    def read_final(self, *_: object, **__: object) -> tuple[bytes, str]:
        self._raise_not_configured()

    def delete_staged(self, *_: object, **__: object) -> None:
        self._raise_not_configured()

    def delete_final(self, *_: object, **__: object) -> None:
        self._raise_not_configured()

    def cleanup_unreferenced_final(self, *_: object, **__: object) -> None:
        return


def _owner_hash(principal_id: str) -> str:
    return hashlib.sha256(principal_id.encode("utf-8")).hexdigest()[:24]


def _valid_final_key(object_key: str, prefix: str) -> bool:
    name = object_key.removeprefix(prefix)
    return bool(re.fullmatch(r"[0-9a-f]{32}\.(png|jpg)", name))
