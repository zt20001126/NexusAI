"""任务结果读取接口的独立响应 DTO。"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskResultDetail(BaseModel):
    """经所有者校验后返回的 JSON 任务结果。"""

    model_config = ConfigDict(extra="forbid")

    task_result_id: str = Field(pattern=r"^[1-9][0-9]{0,18}$")
    agent_id: str
    result_type: str
    generation_status: str
    result_data: dict[str, Any] = Field(default_factory=dict)
