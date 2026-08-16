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
