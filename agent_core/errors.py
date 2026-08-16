"""对外稳定、对内可诊断的智能体业务异常。"""


class AgentFrameworkError(Exception):
    """通用智能体框架可预期异常基类。

    `message` 可以安全返回调用方；真实内部异常必须只写入服务端日志。
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class AgentAlreadyRegisteredError(AgentFrameworkError):
    """同一进程内重复注册智能体标识。"""

    def __init__(self, agent_id: str) -> None:
        del agent_id
        super().__init__("AGENT_ALREADY_REGISTERED", "智能体标识已注册")


class AgentNotFoundError(AgentFrameworkError):
    """调用方指定的智能体不存在。"""

    def __init__(self, agent_id: str) -> None:
        del agent_id
        super().__init__("AGENT_NOT_FOUND", "未找到指定智能体")


class BackendNotConfiguredError(AgentFrameworkError):
    """调用了仅预留但尚未配置的外部基础设施能力。"""

    def __init__(self, backend: str) -> None:
        del backend
        super().__init__("BACKEND_NOT_CONFIGURED", "所需基础设施尚未配置")


class ModelNotConfiguredError(AgentFrameworkError):
    """模型实例被请求，但模型名或密钥尚未配置。"""

    def __init__(self) -> None:
        super().__init__("MODEL_NOT_CONFIGURED", "模型服务尚未配置")


class RunBusyError(AgentFrameworkError):
    """同一会话已有运行，拒绝并发覆盖状态。"""

    def __init__(self) -> None:
        super().__init__("RUN_BUSY", "当前会话正在处理中")


class RunNotResumableError(AgentFrameworkError):
    """目标运行不存在或不处于等待回答状态。"""

    def __init__(self) -> None:
        super().__init__("RUN_NOT_RESUMABLE", "当前运行无法恢复")


class InvalidResumeAnswersError(AgentFrameworkError):
    """恢复答案与当前等待问题不匹配。"""

    def __init__(self) -> None:
        super().__init__("INVALID_RESUME_ANSWERS", "恢复答案与当前问题不匹配")


class RunNotCancellableError(AgentFrameworkError):
    """目标运行不存在、归属不符或已经结束。"""

    def __init__(self) -> None:
        super().__init__("RUN_NOT_CANCELLABLE", "当前运行无法取消")


class ConversationAccessDeniedError(AgentFrameworkError):
    """会话标识已属于其他主体或智能体。"""

    def __init__(self) -> None:
        super().__init__("CONVERSATION_ACCESS_DENIED", "当前会话不可访问")


class AgentDefinitionError(AgentFrameworkError):
    """智能体定义与编译图暴露的运行契约不一致。"""

    def __init__(self) -> None:
        super().__init__("AGENT_DEFINITION_INVALID", "智能体定义不完整或不一致")
