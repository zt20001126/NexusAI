"""简历助手应用层错误及其稳定 HTTP 契约。"""


class ResumeApplicationError(RuntimeError):
    """带稳定错误码和 HTTP 状态的简历业务错误。"""

    code = "RESUME_ERROR"
    message = "简历操作失败"
    status_code = 500


class ResumeNotFoundError(ResumeApplicationError):
    """当前单人主体尚无可导出的简历。"""

    code = "RESUME_NOT_FOUND"
    message = "简历尚未保存"
    status_code = 404


class ResumePhotoNotFoundError(ResumeApplicationError):
    """照片不存在或不是当前单人主体的照片。"""

    code = "RESUME_PHOTO_NOT_FOUND"
    message = "证件照不存在或已过期"
    status_code = 404


class ResumePhotoInvalidError(ResumeApplicationError):
    """上传内容不是受支持的 PNG/JPEG 图片。"""

    code = "RESUME_PHOTO_INVALID"
    message = "仅支持有效的 PNG 或 JPEG 图片"
    status_code = 415


class ResumePhotoTooLargeError(ResumeApplicationError):
    """照片超过允许大小。"""

    code = "RESUME_PHOTO_TOO_LARGE"
    message = "证件照不能超过 5 MiB"
    status_code = 413


class ResumePhotoInvalidIdError(ResumeApplicationError):
    """照片引用 ID 格式不合法。"""

    code = "INVALID_RESUME_PHOTO_ID"
    message = "证件照 ID 格式不正确"
    status_code = 400


class ResumeStorageNotConfiguredError(ResumeApplicationError):
    """照片或 PDF 功能所需的存储、渲染资源未配置。"""

    code = "RESUME_STORAGE_NOT_CONFIGURED"
    message = "简历照片存储尚未配置"
    status_code = 503


class ResumeStorageUnavailableError(ResumeApplicationError):
    """数据库或对象存储暂不可用。"""

    code = "RESUME_STORAGE_UNAVAILABLE"
    message = "简历数据暂时不可用，请稍后重试"
    status_code = 503


class ResumePhotoStorageUnavailableError(ResumeApplicationError):
    """照片 OSS 操作失败。"""

    code = "RESUME_PHOTO_STORAGE_UNAVAILABLE"
    message = "证件照存储暂时不可用，请稍后重试"
    status_code = 502


class ResumePdfUnavailableError(ResumeApplicationError):
    """PDF 渲染器不可用。"""

    code = "RESUME_PDF_UNAVAILABLE"
    message = "PDF 导出服务暂时不可用"
    status_code = 503


class ResumePdfTimeoutError(ResumeApplicationError):
    """PDF 渲染超过配置的时间上限。"""

    code = "RESUME_PDF_TIMEOUT"
    message = "PDF 导出超时，请稍后重试"
    status_code = 504


class ResumePageOverflowError(ResumeApplicationError):
    """简历内容超出单页 A4 可用区域。"""

    code = "RESUME_PAGE_OVERFLOW"
    message = "内容超过单页 A4，请减少内容或调整排版"
    status_code = 422
