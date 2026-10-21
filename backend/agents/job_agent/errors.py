"""求职智能体对外暴露的稳定错误类型，不携带底层异常细节。"""


class JobAgentError(Exception):
    """所有可识别求职智能体错误的共同类型。"""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class JobAgentConfigurationError(JobAgentError):
    """智能体构建配置无效或缺少必要运行上下文。"""


class JobAgentInputError(JobAgentError):
    """用户输入不符合求职智能体约定。"""


class JobAgentExecutionError(JobAgentError):
    """模型或图执行未能完成。"""
