"""应用运行时组装入口，负责装配依赖并管理资源生命周期。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agent.constants import (
    BASE_CONVERSATION_AGENT_ID,
    COMMON_AGENT_ID,
    IMAGE_AGENT_ID,
    LISTING_AGENT_ID,
    LABOR_LAW_AGENT_ID,
    RESEARCH_AGENT_ID,
    LITERATURE_READER_AGENT_ID,
)
from agent.persistence.memory import MemoryEventSequence
from agent.runner import AgentRunner, build_agent_runner
from agent.streaming.publisher import EventPublisher
from agents.base_agent import create_basic_conversation_agent
from agents.image_agent.graph import build_image_agent_graph
from agents.image_agent.providers.result_downloader import ImageResultDownloader
from agents.image_agent.providers.tokenhub_client import TokenHubImageClient
from agents.listing_agent.graph import build_listing_agent_graph
from agents.labor_law_agent.embedding import create_legal_embedding_model
from agents.labor_law_agent.graph import build_labor_law_agent_graph
from agents.labor_law_agent.retrieval import LegalRetrievalService
from agents.literature_reader_agent.embedding import create_literature_embedding_model
from agents.literature_reader_agent.graph import build_literature_reader_agent_graph
from agents.literature_reader_agent.retrieval import LiteratureRetrievalService
from agents.research_agent.graph import build_research_agent_graph
from agents.research_agent.providers.openalex_client import OpenAlexClient
from agents.registry import (
    AgentRegistry,
    PROJECT_AGENT_DEFINITIONS,
)
from app.crud import (
    PostgresConversationStore,
    PostgresMessageStore,
    PostgresLegalKnowledgeStore,
    PostgresLiteratureRepository,
    PostgresRunLock,
    PostgresRunStore,
    PostgresTaskResultStore,
)
from app.db.database import PostgresDatabase
from app.service.agent import AgentApplicationService
from app.service.conversation import ConversationApplicationService
from app.service.health import HealthMonitor
from app.service.research import ResearchApplicationService
from app.service.literature import LiteratureApplicationService
from app.service.task_result import TaskResultApplicationService
from infra.aliyun_oss import AliyunOSSImageStorage
from infra.model_provider import ChatModelProvider, OpenAICompatibleProvider
from infra.object_storage import UnavailableImageObjectStore
from infra.literature_document_storage import (
    AliyunOSSLiteratureStorage,
    UnavailableLiteratureStorage,
)
from infra.health_probes import PostgresHealthProbe, RedisBrokerHealthProbe
from infra.literature_task_queue import CeleryLiteratureTaskQueue
from infra.settings import AppSettings
from infra.snowflake import get_snowflake_generator


def build_lifespan(
    settings: AppSettings,
    model_provider: ChatModelProvider | None,
) -> Callable[[FastAPI], Any]:
    """创建固定使用 PostgreSQL 的应用生命周期。"""

    @asynccontextmanager
    async def lifespan(app_instance: FastAPI) -> AsyncIterator[None]:
        """启动时创建运行组件，退出时释放数据库和 Checkpoint 连接。"""
        if settings.database_url is None:
            raise ValueError("必须配置 DATABASE_URL 才能启动应用")
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        async with AsyncPostgresSaver.from_conn_string(
            settings.database_url.replace("postgresql+psycopg://", "postgresql://", 1)
        ) as checkpointer:
            await checkpointer.setup()
            id_generator = get_snowflake_generator(settings.snowflake_worker_id)
            image_storage = (
                AliyunOSSImageStorage(settings, id_generator)
                if settings.aliyun_oss_configured
                else UnavailableImageObjectStore()
            )
            literature_storage = (
                AliyunOSSLiteratureStorage(settings)
                if settings.aliyun_oss_configured
                else UnavailableLiteratureStorage()
            )
            with PostgresDatabase(settings.database_url, id_generator) as database:
                conversation_store = PostgresConversationStore(database)
                message_store = PostgresMessageStore(database)
                task_result_store = PostgresTaskResultStore(database)

                def create_postgres_runner(
                    agent_id: str,
                    graph: Any | None = None,
                    attachment_store: Any | None = None,
                ) -> AgentRunner:
                    """使用当前 PostgreSQL 运行时组装智能体 Runner。"""
                    return build_agent_runner(
                        settings=settings,
                        checkpointer=checkpointer,
                        run_store=PostgresRunStore(database),
                        run_lock=PostgresRunLock(database),
                        conversation_store=conversation_store,
                        message_store=message_store,
                        event_sequence=MemoryEventSequence(),
                        model_provider=model_provider,
                        graph=graph,
                        agent_id=agent_id,
                        task_result_store=task_result_store,
                        attachment_store=attachment_store,
                        id_generator=id_generator,
                    )

                runner = create_postgres_runner(COMMON_AGENT_ID)
                resolved_model_provider = model_provider or OpenAICompatibleProvider(settings)
                basic_conversation_agent = create_basic_conversation_agent(
                    agent_id=BASE_CONVERSATION_AGENT_ID,
                    chat_model=resolved_model_provider.create_chat_model(),
                    checkpointer=checkpointer,
                )
                basic_conversation_runner = create_postgres_runner(
                    agent_id=BASE_CONVERSATION_AGENT_ID,
                    graph=basic_conversation_agent.compiled_graph,
                )
                image_model = resolved_model_provider.create_chat_model()
                image_graph = build_image_agent_graph(
                    checkpointer,
                    image_model,
                    settings,
                    TokenHubImageClient(settings),
                    ImageResultDownloader(
                        timeout_seconds=settings.tokenhub_timeout_seconds,
                        max_bytes=settings.image_result_max_bytes,
                    ),
                    task_result_store,
                    image_storage,
                )
                image_runner = create_postgres_runner(
                    agent_id=IMAGE_AGENT_ID,
                    graph=image_graph,
                    attachment_store=image_storage,
                )
                listing_graph = build_listing_agent_graph(
                    checkpointer,
                    resolved_model_provider.create_chat_model(),
                    task_result_store,
                    image_storage,
                )
                listing_runner = create_postgres_runner(
                    agent_id=LISTING_AGENT_ID,
                    graph=listing_graph,
                    attachment_store=image_storage,
                )
                research_graph = build_research_agent_graph(
                    checkpointer,
                    resolved_model_provider.create_chat_model(),
                    OpenAlexClient(settings),
                    task_result_store,
                    settings.research_max_search_rounds,
                )
                research_runner = create_postgres_runner(
                    agent_id=RESEARCH_AGENT_ID,
                    graph=research_graph,
                )
                legal_knowledge_store = PostgresLegalKnowledgeStore(database)
                legal_retrieval_service = LegalRetrievalService(
                    repository=legal_knowledge_store,
                    embedding_model=create_legal_embedding_model(settings),
                    top_k=settings.legal_rag_top_k,
                    candidate_count=settings.legal_rag_candidate_count,
                    min_similarity=settings.legal_rag_min_similarity,
                )
                labor_law_graph = build_labor_law_agent_graph(
                    checkpointer,
                    resolved_model_provider.create_chat_model(),
                    legal_retrieval_service,
                    settings.legal_rag_max_context_chars,
                )
                labor_law_runner = create_postgres_runner(
                    agent_id=LABOR_LAW_AGENT_ID,
                    graph=labor_law_graph,
                )
                literature_repository = PostgresLiteratureRepository(database)
                literature_retrieval_service = LiteratureRetrievalService(
                    repository=literature_repository,
                    embedding_model=create_literature_embedding_model(settings),
                    top_k=settings.literature_top_k,
                    candidate_count=settings.literature_candidate_count,
                    min_similarity=settings.literature_min_similarity,
                    context_max_chars=settings.literature_context_max_chars,
                    chunk_max_chars=settings.literature_chunk_max_chars,
                )
                literature_graph = build_literature_reader_agent_graph(
                    checkpointer,
                    resolved_model_provider.create_chat_model(),
                    literature_retrieval_service,
                    literature_repository,
                )
                literature_runner = create_postgres_runner(
                    agent_id=LITERATURE_READER_AGENT_ID,
                    graph=literature_graph,
                )
                _install_runtime_state(
                    app_instance,
                    settings,
                    {
                        COMMON_AGENT_ID: runner,
                        BASE_CONVERSATION_AGENT_ID: basic_conversation_runner,
                        IMAGE_AGENT_ID: image_runner,
                        LISTING_AGENT_ID: listing_runner,
                        RESEARCH_AGENT_ID: research_runner,
                        LABOR_LAW_AGENT_ID: labor_law_runner,
                        LITERATURE_READER_AGENT_ID: literature_runner,
                    },
                    MemoryEventSequence(),
                    conversation_store,
                    message_store,
                    task_result_store,
                    image_storage,
                )
                app_instance.state.literature_service = LiteratureApplicationService(
                    repository=literature_repository,
                    storage=literature_storage,
                    task_queue=CeleryLiteratureTaskQueue(),
                    chat_service=app_instance.state.agent_registry.get_service(
                        LITERATURE_READER_AGENT_ID
                    ),
                    settings=settings,
                    id_generator=id_generator,
                )
                postgres_probe = PostgresHealthProbe(
                    settings.database_url,
                    settings.health_check_timeout_seconds,
                )
                redis_probe = RedisBrokerHealthProbe(
                    settings.celery_broker_url,
                    settings.health_check_timeout_seconds,
                )
                health_monitor = HealthMonitor(
                    [postgres_probe, redis_probe],
                    interval_seconds=settings.health_check_interval_seconds,
                    timeout_seconds=settings.health_check_timeout_seconds,
                )
                app_instance.state.health_monitor = health_monitor
                try:
                    await health_monitor.start()
                    yield
                finally:
                    await health_monitor.stop()
                    await redis_probe.aclose()

    return lifespan


def _install_runtime_state(
    app_instance: FastAPI,
    settings: AppSettings,
    runners: dict[str, Any],
    event_sequence: Any,
    conversation_store: PostgresConversationStore,
    message_store: PostgresMessageStore,
    task_result_store: PostgresTaskResultStore,
    attachment_store: Any,
) -> None:
    """组装注册表、共享事件发布器和查询服务。"""
    publisher = EventPublisher(event_sequence, settings.sse_heartbeat_seconds)
    services = {
        agent_id: AgentApplicationService(runner, publisher)
        for agent_id, runner in runners.items()
    }
    registry = AgentRegistry(PROJECT_AGENT_DEFINITIONS, services)
    app_instance.state.settings = settings
    app_instance.state.agent_registry = registry
    app_instance.state.agent_runner = runners[COMMON_AGENT_ID]
    app_instance.state.agent_service = services[COMMON_AGENT_ID]
    app_instance.state.task_result_store = task_result_store
    task_result_service = TaskResultApplicationService(task_result_store)
    app_instance.state.task_result_service = task_result_service
    app_instance.state.research_service = ResearchApplicationService(
        services[RESEARCH_AGENT_ID],
        task_result_service,
    )
    app_instance.state.attachment_store = attachment_store
    app_instance.state.conversation_service = ConversationApplicationService(
        conversation_store,
        message_store,
        task_result_store,
    )
