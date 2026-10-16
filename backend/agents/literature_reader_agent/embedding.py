"""构造复用项目 TokenHub 配置的文献 Embedding 客户端。"""

from langchain_openai import OpenAIEmbeddings

from agents.labor_law_agent.constants import LEGAL_EMBEDDING_BATCH_SIZE
from agents.labor_law_agent.embedding import create_legal_embedding_model
from infra.settings import AppSettings


def create_literature_embedding_model(settings: AppSettings) -> OpenAIEmbeddings | None:
    """复用已配置的 TokenHub 模型、密钥和 1024 维参数。"""
    return create_legal_embedding_model(settings)


__all__ = ["create_literature_embedding_model", "LEGAL_EMBEDDING_BATCH_SIZE"]

