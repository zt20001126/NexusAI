"""导入劳动法律知识库的命令行入口。"""

import logging

from agents.labor_law_agent.embedding import create_legal_embedding_model
from agents.labor_law_agent.service import LegalKnowledgeService
from app.crud import PostgresLegalKnowledgeStore
from app.db.database import PostgresDatabase
from infra.settings import AppSettings


def main() -> None:
    """读取配置并将智能体目录内的法规语料导入 PostgreSQL + pgvector。"""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = AppSettings()
    if not settings.database_url:
        raise RuntimeError("请先在 backend/.env 中配置 DATABASE_URL")
    embedding_model = create_legal_embedding_model(settings)
    if embedding_model is None:
        raise RuntimeError("请先配置 TENCENT_TOKENHUB_API_KEY")
    with PostgresDatabase(settings.database_url) as database:
        service = LegalKnowledgeService(
            PostgresLegalKnowledgeStore(database),
            embedding_model,
        )
        imported_count = service.import_manifest()
    print(f"已导入 {imported_count} 部现行劳动法律法规。")


if __name__ == "__main__":
    main()

