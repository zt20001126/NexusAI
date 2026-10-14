"""图片对象存储边界，用于隔离 OSS 配置缺失和上游访问错误。"""

from dataclasses import dataclass


class ObjectStorageError(RuntimeError):
    """对象存储读写失败的安全业务错误，不包含密钥或完整上游响应。"""


class ObjectStorageNotConfiguredError(ObjectStorageError):
    """阿里云 OSS 配置缺失时返回给图片上传和生图流程的错误。"""


@dataclass(frozen=True)
class StoredImageObject:
    """OSS 图片对象的数据库元数据；图片字节保留在对象存储中。"""

    object_key: str
    mime_type: str
    file_size: int


class UnavailableImageObjectStore:
    """OSS 未配置时的适配器；保留非图片智能体可启动能力。"""

    def __init__(self) -> None:
        """创建未配置适配器。"""

    @staticmethod
    def _raise_not_configured() -> None:
        """用统一错误拒绝依赖 OSS 的操作。"""
        raise ObjectStorageNotConfiguredError(
            "图片存储尚未配置，请在后端环境变量中填写阿里云 OSS 参数"
        )

    def save(self, *_: object, **__: object) -> object:
        """拒绝上传参考图片。"""
        self._raise_not_configured()

    def validate_staged(self, *_: object, **__: object) -> None:
        """拒绝验证尚未写入 OSS 的参考图片。"""
        self._raise_not_configured()

    def bind_to_message(self, *_: object, **__: object) -> None:
        """拒绝绑定尚未写入 OSS 的参考图片。"""
        self._raise_not_configured()

    def list_for_generation(self, *_: object, **__: object) -> object:
        """拒绝读取尚未写入 OSS 的参考图片。"""
        self._raise_not_configured()

    def save_result(self, *_: object, **__: object) -> StoredImageObject:
        """拒绝保存生成结果。"""
        self._raise_not_configured()

    def read_result(self, *_: object, **__: object) -> tuple[bytes, str]:
        """拒绝读取生成结果。"""
        self._raise_not_configured()
