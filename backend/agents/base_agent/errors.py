"""基座对外暴露的稳定错误类型，不携带底层异常细节。"""


class BaseAgentError(Exception):
    """所有可识别基座错误的共同类型。"""

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class BaseAgentConfigurationError(BaseAgentError):
    """智能体构建配置无效或缺少必要运行上下文。"""


class BaseAgentInputError(BaseAgentError):
    """用户输入不符合基座约定。"""


class BaseAgentExecutionError(BaseAgentError):
    """模型或图执行未能完成。"""
