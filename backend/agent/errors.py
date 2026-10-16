"""对外稳定、对内可诊断的智能体业务异常。"""


class AgentError(Exception):
    """智能体可预期异常基类，消息可以安全返回调用方。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class BackendNotConfiguredError(AgentError):
    """外部基础设施尚未配置。"""

    def __init__(self, backend: str) -> None:
        del backend
        super().__init__("BACKEND_NOT_CONFIGURED", "所需基础设施尚未配置")


class ModelNotConfiguredError(AgentError):
    """模型服务尚未配置。"""

    def __init__(self) -> None:
        super().__init__("MODEL_NOT_CONFIGURED", "模型服务尚未配置")


class RunBusyError(AgentError):
    """同一会话已有运行。"""

    def __init__(self) -> None:
        super().__init__("RUN_BUSY", "当前会话正在处理中")


class RunNotResumableError(AgentError):
    """目标运行不能恢复。"""

    def __init__(self) -> None:
        super().__init__("RUN_NOT_RESUMABLE", "当前运行无法恢复")


class InvalidResumeAnswersError(AgentError):
    """恢复答案与待回答问题不匹配。"""

    def __init__(self) -> None:
        super().__init__("INVALID_RESUME_ANSWERS", "恢复答案与当前问题不匹配")


class RunNotCancellableError(AgentError):
    """目标运行不能取消。"""

    def __init__(self) -> None:
        super().__init__("RUN_NOT_CANCELLABLE", "当前运行无法取消")


class ConversationAccessDeniedError(AgentError):
    """会话不属于当前可信主体。"""

    def __init__(self) -> None:
        super().__init__("CONVERSATION_ACCESS_DENIED", "当前会话不可访问")


class AttachmentAccessDeniedError(AgentError):
    """上传附件不属于当前主体或会话。"""

    def __init__(self) -> None:
        super().__init__("ATTACHMENT_ACCESS_DENIED", "上传图片不可访问")


class UnknownAgentError(AgentError):
    """请求的智能体尚未注册。"""

    def __init__(self) -> None:
        super().__init__("UNKNOWN_AGENT", "请求的智能体不存在")


class LiteratureDocumentNotFoundError(AgentError):
    """文献不存在或不属于当前可信主体。"""

    def __init__(self) -> None:
        super().__init__("LITERATURE_DOCUMENT_NOT_FOUND", "文献不存在或不可访问")


class LiteratureDocumentNotReadyError(AgentError):
    """所选文献仍在处理或入库失败。"""

    def __init__(self) -> None:
        super().__init__(
            "LITERATURE_DOCUMENT_NOT_READY",
            "所选文献尚未完成处理，请等待入库成功后再提问",
        )


class LiteratureQueueUnavailableError(AgentError):
    """文献异步处理任务无法发送到 Broker。"""

    def __init__(self) -> None:
        super().__init__(
            "LITERATURE_QUEUE_UNAVAILABLE",
            "文献处理队列暂时不可用，请稍后重试",
        )
