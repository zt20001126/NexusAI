"""集中导出应用 ORM 模型并确保其表注册到共享元数据。"""

from app.models.base import Base
from app.models.conversation import Conversation
from app.models.identity import UserIdentity
from app.models.legal_knowledge import LegalArticle, LegalDocument, LegalLawVersion
from app.models.message import Message
from app.models.run import AgentRun
from app.models.task_result import TaskResult

__all__ = [
    "AgentRun",
    "Base",
    "Conversation",
    "Message",
    "LegalArticle",
    "LegalDocument",
    "LegalLawVersion",
    "TaskResult",
    "UserIdentity",
]
