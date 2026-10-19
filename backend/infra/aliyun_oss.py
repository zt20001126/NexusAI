"""阿里云 OSS 图片对象存储适配器，Bucket 应设置为私有。"""

from __future__ import annotations

import base64
import hashlib
import logging
import re
from typing import Any

from agent.errors import AttachmentAccessDeniedError
from agent.schemas.task_result import ImageAttachmentRecord
from infra.object_storage import ObjectStorageError, StoredImageObject
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator


logger = logging.getLogger(__name__)
_ALLOWED_MIME_TYPES = frozenset({"image/png", "image/jpeg"})
_NUMERIC_ID_PATTERN = re.compile(r"^[1-9][0-9]{0,18}$")
_LEGACY_ATTACHMENT_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_MIME_EXTENSIONS = {"image/png": "png", "image/jpeg": "jpg"}


class AliyunOSSImageStorage:
    """将参考图和生成图存入私有 OSS，并按可信主体校验对象归属。"""

    def __init__(
        self,
        settings: AppSettings,
        id_generator: SnowflakeIdGenerator | None = None,
    ) -> None:
        """基于环境配置创建 OSS Bucket 客户端；不在代码中保存任何密钥。"""
        if not settings.aliyun_oss_configured:
            raise ValueError("阿里云 OSS 参数不完整")
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
        self._upload_max_bytes = settings.image_upload_max_bytes
        self._result_max_bytes = settings.image_result_max_bytes
        self._id_generator = id_generator or get_snowflake_generator(
            settings.snowflake_worker_id
        )

    def save(
        self,
        user_id: str,
        file_name: str,
        mime_type: str,
        image_data: bytes,
    ) -> ImageAttachmentRecord:
        """上传参考图片并返回对象 ID；数据库不保存图片字节或附件行。"""
        self._validate_image(mime_type, image_data, self._upload_max_bytes)
        attachment_id = self._id_generator.next_id_string()
        owner_hash = _owner_hash(user_id)
        object_key = self._key("staged", owner_hash, attachment_id)
        self._put_object(object_key, image_data, mime_type, owner_hash, file_name)
        return ImageAttachmentRecord(
            attachment_id=attachment_id,
            user_id=user_id,
            conversation_id=None,
            message_id=None,
            file_name=file_name,
            mime_type=mime_type,
            file_size=len(image_data),
            image_data=b"",
            status="staged",
            object_key=object_key,
        )

    def validate_staged(self, attachment_ids: list[str], user_id: str) -> None:
        """检查参考图存在且对象元数据中的上传主体与当前用户一致。"""
        if len(attachment_ids) != len(set(attachment_ids)):
            raise AttachmentAccessDeniedError()
        owner_hash = _owner_hash(user_id)
        for attachment_id in attachment_ids:
            self._validate_attachment_id(attachment_id)
            self._get_reference_metadata(owner_hash, attachment_id, prefix="staged")

    def bind_to_message(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
        message_id: str,
    ) -> None:
        """确认附件归属；附件关联随任务输入写入 task_results.input。"""
        del conversation_id, message_id
        self.validate_staged(attachment_ids, user_id)
        owner_hash = _owner_hash(user_id)
        for attachment_id in attachment_ids:
            source_key = self._key("staged", owner_hash, attachment_id)
            target_key = self._key("references", owner_hash, attachment_id)
            try:
                self._bucket.copy_object(self._bucket_name, source_key, target_key)
                self._bucket.delete_object(source_key)
            except self._oss2.exceptions.OssError as error:
                self._raise_storage_error("promote_reference", error)

    def list_for_generation(
        self,
        attachment_ids: list[str],
        user_id: str,
        conversation_id: str,
    ) -> list[ImageAttachmentRecord]:
        """读取当前用户拥有的 OSS 参考图片，供图片 API 组装请求。"""
        del conversation_id
        if len(attachment_ids) != len(set(attachment_ids)):
            raise AttachmentAccessDeniedError()
        owner_hash = _owner_hash(user_id)
        return [
            self._load_reference(owner_hash, user_id, attachment_id)
            for attachment_id in attachment_ids
        ]

    def save_result(
        self,
        user_id: str,
        task_result_id: str,
        image_data: bytes,
        mime_type: str,
    ) -> StoredImageObject:
        """把第三方返回的图片写入 OSS，并返回可持久化的对象元数据。"""
        self._validate_numeric_id(task_result_id)
        self._validate_image(mime_type, image_data, self._result_max_bytes)
        owner_hash = _owner_hash(user_id)
        object_key = self._key(
            "generated",
            owner_hash,
            f"{task_result_id}.{_MIME_EXTENSIONS[mime_type]}",
        )
        self._put_object(object_key, image_data, mime_type, owner_hash)
        return StoredImageObject(object_key, mime_type, len(image_data))

    def migrate_legacy_result(
        self,
        user_id: str,
        legacy_task_result_id: str,
        image_data: bytes,
        mime_type: str,
    ) -> StoredImageObject:
        """升级旧数据库时按原任务 ID 将 PostgreSQL 图片字节转存到 OSS。"""
        if not re.fullmatch(r"[0-9a-fA-F-]{1,64}", legacy_task_result_id):
            raise ValueError("旧任务结果 ID 格式不合法")
        self._validate_image(mime_type, image_data, self._result_max_bytes)
        owner_hash = _owner_hash(user_id)
        object_key = self._key(
            "generated",
            owner_hash,
            f"legacy-{legacy_task_result_id}.{_MIME_EXTENSIONS[mime_type]}",
        )
        self._put_object(object_key, image_data, mime_type, owner_hash)
        return StoredImageObject(object_key, mime_type, len(image_data))

    def migrate_legacy_reference(
        self,
        user_id: str,
        legacy_attachment_id: str,
        file_name: str,
        mime_type: str,
        image_data: bytes,
    ) -> StoredImageObject:
        """升级旧附件表时保留附件标识，将图片字节转存到永久参考图前缀。"""
        self._validate_attachment_id(legacy_attachment_id)
        self._validate_image(mime_type, image_data, self._upload_max_bytes)
        owner_hash = _owner_hash(user_id)
        object_key = self._key("references", owner_hash, legacy_attachment_id)
        self._put_object(object_key, image_data, mime_type, owner_hash, file_name)
        return StoredImageObject(object_key, mime_type, len(image_data))

    def read_result(self, object_key: str, user_id: str) -> tuple[bytes, str]:
        """按任务结果中的对象键读取图片，并再次校验 OSS 对象归属。"""
        owner_hash = _owner_hash(user_id)
        expected_prefix = self._key("generated", owner_hash, "")
        if not object_key.startswith(expected_prefix) or ".." in object_key.split("/"):
            raise AttachmentAccessDeniedError()
        return self._read_object(object_key, owner_hash, self._result_max_bytes)

    def read_reference(self, attachment_id: str, user_id: str) -> tuple[bytes, str]:
        """按主体从永久参考图前缀读取已发送图片。"""
        self._validate_attachment_id(attachment_id)
        owner_hash = _owner_hash(user_id)
        object_key = self._key("references", owner_hash, attachment_id)
        return self._read_object(object_key, owner_hash, self._upload_max_bytes)

    def _load_reference(
        self,
        owner_hash: str,
        user_id: str,
        attachment_id: str,
    ) -> ImageAttachmentRecord:
        """读取一个参考图并恢复生成工具使用的领域记录。"""
        self._validate_attachment_id(attachment_id)
        object_key = self._key("references", owner_hash, attachment_id)
        image_data, mime_type, headers = self._read_object_with_metadata(
            object_key,
            owner_hash,
            self._upload_max_bytes,
        )
        return ImageAttachmentRecord(
            attachment_id=attachment_id,
            user_id=user_id,
            conversation_id=None,
            message_id=None,
            file_name=_decode_file_name(headers, attachment_id, mime_type),
            mime_type=mime_type,
            file_size=len(image_data),
            image_data=image_data,
            status="staged",
            object_key=object_key,
        )

    def _get_reference_metadata(
        self,
        owner_hash: str,
        attachment_id: str,
        *,
        prefix: str,
    ) -> None:
        """在不下载字节的情况下检查参考对象存在、归属和大小。"""
        object_key = self._key(prefix, owner_hash, attachment_id)
        try:
            metadata = self._bucket.head_object(object_key)
            headers = _normalize_headers(metadata.headers)
        except self._oss2.exceptions.OssError as error:
            if getattr(error, "status", None) == 404:
                raise AttachmentAccessDeniedError() from None
            self._raise_storage_error("head_reference", error)
        if headers.get("x-oss-meta-owner-hash") != owner_hash:
            raise AttachmentAccessDeniedError()
        if headers.get("content-type") not in _ALLOWED_MIME_TYPES:
            raise AttachmentAccessDeniedError()
        if int(headers.get("content-length", "0")) > self._upload_max_bytes:
            raise AttachmentAccessDeniedError()

    def _read_object(
        self,
        object_key: str,
        owner_hash: str,
        max_bytes: int,
    ) -> tuple[bytes, str]:
        """读取限定大小的图片对象并验证其主体元数据。"""
        image_data, mime_type, _ = self._read_object_with_metadata(
            object_key,
            owner_hash,
            max_bytes,
        )
        return image_data, mime_type

    def _read_object_with_metadata(
        self,
        object_key: str,
        owner_hash: str,
        max_bytes: int,
    ) -> tuple[bytes, str, dict[str, str]]:
        """从 OSS 读取对象，先检查元信息再限制响应字节数。"""
        try:
            response = self._bucket.get_object(object_key)
            headers = _normalize_headers(response.headers)
            if headers.get("x-oss-meta-owner-hash") != owner_hash:
                raise AttachmentAccessDeniedError()
            mime_type = headers.get("content-type", "")
            if mime_type not in _ALLOWED_MIME_TYPES:
                raise AttachmentAccessDeniedError()
            if int(headers.get("content-length", "0")) > max_bytes:
                raise AttachmentAccessDeniedError()
            try:
                image_data = response.read(max_bytes + 1)
            finally:
                response.close()
        except AttachmentAccessDeniedError:
            raise
        except self._oss2.exceptions.OssError as error:
            if getattr(error, "status", None) == 404:
                raise AttachmentAccessDeniedError() from None
            self._raise_storage_error("get_object", error)
        if len(image_data) > max_bytes:
            raise AttachmentAccessDeniedError()
        self._validate_image(mime_type, image_data, max_bytes)
        return image_data, mime_type, dict(headers)

    def _put_object(
        self,
        object_key: str,
        image_data: bytes,
        mime_type: str,
        owner_hash: str,
        file_name: str | None = None,
    ) -> None:
        """将图片写入私有 Bucket，并为后续访问授权记录主体摘要。"""
        headers = {
            "Content-Type": mime_type,
            "x-oss-meta-owner-hash": owner_hash,
            "x-oss-meta-sha256": hashlib.sha256(image_data).hexdigest(),
        }
        if file_name is not None:
            headers["x-oss-meta-file-name"] = base64.urlsafe_b64encode(
                file_name.encode("utf-8")
            ).decode("ascii")
        try:
            self._bucket.put_object(object_key, image_data, headers=headers)
        except self._oss2.exceptions.OssError as error:
            self._raise_storage_error("put_object", error)

    def _key(self, *parts: str) -> str:
        """组合不含用户原始身份信息的对象键。"""
        prefix = [self._prefix] if self._prefix else []
        return "/".join(prefix + list(parts))

    def _raise_storage_error(self, operation: str, error: Exception) -> None:
        """记录非敏感的操作上下文并屏蔽上游响应细节。"""
        logger.exception(
            "阿里云 OSS 操作失败 operation=%s bucket=%s",
            operation,
            self._bucket_name,
            exc_info=error,
        )
        raise ObjectStorageError("阿里云 OSS 图片读写失败") from None

    @staticmethod
    def _validate_image(mime_type: str, image_data: bytes, max_bytes: int) -> None:
        """限制图片格式、大小并验证 PNG/JPEG 文件签名。"""
        if mime_type not in _ALLOWED_MIME_TYPES or not image_data or len(image_data) > max_bytes:
            raise AttachmentAccessDeniedError()
        valid_signature = (
            image_data.startswith(b"\x89PNG\r\n\x1a\n")
            if mime_type == "image/png"
            else image_data.startswith(b"\xff\xd8\xff")
        )
        if not valid_signature:
            raise AttachmentAccessDeniedError()

    @staticmethod
    def _validate_attachment_id(attachment_id: str) -> None:
        """接受雪花附件 ID，并兼容迁移期遗留的 UUID hex 附件 ID。"""
        if not (
            _NUMERIC_ID_PATTERN.fullmatch(attachment_id)
            or _LEGACY_ATTACHMENT_ID_PATTERN.fullmatch(attachment_id)
        ):
            raise AttachmentAccessDeniedError()

    @staticmethod
    def _validate_numeric_id(value: str) -> None:
        """确保结果对象键使用应用生成的雪花任务结果 ID。"""
        if not _NUMERIC_ID_PATTERN.fullmatch(value):
            raise ValueError("任务结果 ID 必须是十进制雪花 ID")


def _owner_hash(user_id: str) -> str:
    """用不可逆主体摘要隔离对象前缀，避免将认证标识写入 OSS 路径。"""
    return hashlib.sha256(user_id.encode("utf-8")).hexdigest()[:32]


def _decode_file_name(headers: dict[str, str], attachment_id: str, mime_type: str) -> str:
    """还原上传时写入 OSS 元数据的文件名。"""
    encoded_name = headers.get("x-oss-meta-file-name")
    if encoded_name:
        try:
            return base64.urlsafe_b64decode(encoded_name.encode("ascii")).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            logger.warning("OSS 参考图文件名元数据无效 attachment_id=%s", attachment_id)
    return f"{attachment_id}.{_MIME_EXTENSIONS[mime_type]}"


def _normalize_headers(headers: Any) -> dict[str, str]:
    """统一 OSS HTTP 响应头大小写，避免转换普通 dict 后丢失大小写不敏感行为。"""
    return {str(key).lower(): str(value) for key, value in headers.items()}
