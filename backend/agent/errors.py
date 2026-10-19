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


class AgentEventStreamExpiredError(AgentError):
    """目标游标早于 Redis Stream 当前保留范围。"""

    def __init__(self) -> None:
        super().__init__("EVENT_STREAM_EXPIRED", "事件流已过期，请重新加载会话历史")


class AgentEventCursorInvalidError(AgentError):
    """恢复游标超出该运行已生成的事件范围。"""

    def __init__(self) -> None:
        super().__init__("EVENT_CURSOR_INVALID", "事件游标超出当前运行范围，请重新加载会话历史")


class AgentEventStoreUnavailableError(AgentError):
    """Redis Stream 或共享取消存储暂时不可用。"""

    def __init__(self) -> None:
        super().__init__("EVENT_STORE_UNAVAILABLE", "会话事件服务暂时不可用，请稍后重试")


class AgentRunRequestConflictError(AgentError):
    """同一请求幂等键被用于不同输入。"""

    def __init__(self) -> None:
        super().__init__("REQUEST_ID_CONFLICT", "请求标识已用于其他消息，请重新提交")


class AgentRunPreparationPendingError(AgentError):
    """幂等请求的首个准备事务尚未保存完输入消息。"""

    def __init__(self) -> None:
        super().__init__("RUN_PREPARATION_PENDING", "本轮正在准备，请稍后重试")


class DuplicateAgentRunRequest(Exception):
    """数据库唯一约束发现并发创建了相同 request_id 的运行。"""


class AgentRunNotFoundError(AgentError):
    """指定会话中没有当前主体可访问的运行记录。"""

    def __init__(self) -> None:
        super().__init__("RUN_NOT_FOUND", "运行记录不存在或不可访问")


class AgentRunAmbiguousError(AgentError):
    """没有 run_id 时会话存在多个可监听活动运行。"""

    def __init__(self) -> None:
        super().__init__("RUN_ID_REQUIRED", "该会话有多个活动运行，请提供 run_id")


class AgentRunAlreadyEndedError(AgentError):
    """运行已经结束且没有可发送的新事件，需要回退到会话历史。"""

    def __init__(self) -> None:
        super().__init__("RUN_ALREADY_ENDED", "本轮已结束，请重新加载会话历史")


class AgentTaskQueueUnavailableError(AgentError):
    """Agent Worker 队列暂时不可用。"""

    def __init__(self) -> None:
        super().__init__("AGENT_QUEUE_UNAVAILABLE", "智能体任务暂时无法启动，请稍后重试")


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
