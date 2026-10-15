"""独立智能体对外展示与运行能力描述。"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class AgentDefinition:
    """注册中心使用的智能体描述，不包含请求级状态。"""

    agent_id: str
    name: str
    description: str
    supports_image_upload: bool


GraphFactory = Callable[..., Any]
