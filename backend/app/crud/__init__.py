"""应用 CRUD 数据访问层，按持久化实体导出 PostgreSQL 适配器。"""

from app.crud.conversation import PostgresConversationStore
from app.crud.message import PostgresMessageStore
from app.crud.legal_knowledge import PostgresLegalKnowledgeStore
from app.crud.literature import PostgresLiteratureRepository
from app.crud.run import PostgresRunStore
from app.crud.run_lock import PostgresRunLock
from app.crud.resume import PostgresResumeRepository
from app.crud.task_result import PostgresTaskResultStore

__all__ = [
    "PostgresConversationStore",
    "PostgresMessageStore",
    "PostgresLegalKnowledgeStore",
    "PostgresLiteratureRepository",
    "PostgresRunLock",
    "PostgresRunStore",
    "PostgresResumeRepository",
    "PostgresTaskResultStore",
]
