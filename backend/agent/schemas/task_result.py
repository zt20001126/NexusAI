"""统一任务结果与输入图片附件的领域记录。"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from agent.enums import AgentType


class TaskResultStatus(StrEnum):
    """统一生成结果生命周期状态。"""

    PENDING = "pending"
    AWAITING_INPUT = "awaiting_input"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskResultRecord:
    """一个智能体产出的业务结果；运行和身份字段只用于写入校验。"""

    task_result_id: str
    agent: AgentType
    user_id: str
    conversation_id: str
    run_id: str | None
    message_id: str | None
    result_type: str
    generation_status: TaskResultStatus
    input_data: dict[str, object] = field(default_factory=dict)
    result_data: dict[str, object] = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True)
class ImageAttachmentRecord:
    """用户上传的参考图片，字节数据只在授权的服务端调用中读取。"""

    attachment_id: str
    user_id: str
    conversation_id: str | None
    message_id: str | None
    file_name: str
    mime_type: str
    file_size: int
    image_data: bytes
    status: str
    object_key: str | None = None
    created_at: datetime | None = None
