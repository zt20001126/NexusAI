"""业务工具面向模型和运行时的统一返回契约。"""

from typing import Any

from pydantic import BaseModel, Field


class ToolResult(BaseModel):
    """工具执行结果；失败消息必须是可安全展示的稳定文本。"""

    success: bool
    data: dict[str, Any] = Field(default_factory=dict)
    code: str = "OK"
    message: str = "执行成功"

