"""构造劳动法律 RAG 使用的 OpenAI-compatible Embedding 客户端。"""

from langchain_openai import OpenAIEmbeddings

from agents.labor_law_agent.constants import LEGAL_EMBEDDING_BATCH_SIZE
from infra.settings import AppSettings


def create_legal_embedding_model(settings: AppSettings) -> OpenAIEmbeddings | None:
    """按配置创建向量模型；未配置 API Key 时返回 None 以允许应用启动。"""
    api_key = settings.tokenhub_api_key.get_secret_value().strip()
    if not api_key or api_key.startswith("replace_with_"):
        return None
    return OpenAIEmbeddings(
        model=settings.legal_embedding_model,
        api_key=api_key,
        base_url=settings.legal_embedding_base_url,
        # TokenHub Kinfra 接受文本字符串；禁用 LangChain 默认的 token ID 预处理。
        check_embedding_ctx_length=False,
        # TokenHub 的向量接口仅支持 float 编码，显式覆盖 OpenAI 客户端默认值。
        model_kwargs={"encoding_format": "float"},
        chunk_size=LEGAL_EMBEDDING_BATCH_SIZE,
        request_timeout=settings.legal_embedding_timeout_seconds,
        max_retries=settings.legal_embedding_max_retries,
    )

