"""应用运行时组装入口，负责装配依赖并管理资源生命周期。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agent.enums import AgentType
from agent.constants import (
    BASE_CONVERSATION_AGENT,
    COMMON_AGENT,
    IMAGE_AGENT,
    LISTING_AGENT,
    LABOR_LAW_AGENT,
    RESEARCH_AGENT,
    LITERATURE_READER_AGENT,
    JOB_AGENT,
    JOB_AGENT_MAX_QUESTION_ROUNDS_PER_RUN,
    MAX_QUESTION_ROUNDS_PER_RUN,
)
from agent.persistence.memory import MemoryEventSequence
from agent.runner import AgentRunner, build_agent_runner
from agent.streaming.publisher import EventPublisher
from agents.base_agent import create_basic_conversation_agent
from agents.job_agent import create_job_agent
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
    PostgresResumeRepository,
)
from app.crud.auth import PostgresAuthRepository
from app.db.database import PostgresDatabase
from app.service.agent import AgentApplicationService, AgentSessionApplicationService
from app.service.auth import AuthApplicationService
from app.service.conversation import ConversationApplicationService
from app.service.health import HealthMonitor
from app.service.job_resume import SavedJobResumeReader
from app.service.research import ResearchApplicationService
from app.service.literature import LiteratureApplicationService
from app.service.task_result import TaskResultApplicationService
from app.service.resume import ResumeApplicationService
from app.service.resume_pdf import PlaywrightResumePdfRenderer
from infra.aliyun_oss import AliyunOSSImageStorage
from infra.model_provider import ChatModelProvider, OpenAICompatibleProvider
from infra.object_storage import UnavailableImageObjectStore
from infra.literature_document_storage import (
    AliyunOSSLiteratureStorage,
    UnavailableLiteratureStorage,
)
from infra.resume_photo_storage import (
    AliyunOSSResumePhotoStorage,
    UnavailableResumePhotoStorage,
)
from infra.health_probes import PostgresHealthProbe, RedisBrokerHealthProbe
from infra.literature_task_queue import CeleryLiteratureTaskQueue
from infra.agent_event_store import RedisAgentEventStore
from infra.agent_task_queue import CeleryAgentTaskQueue
from infra.email_sender import SmtpEmailSender
from infra.redis_auth_store import RedisAuthStore
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
            resume_photo_storage = (
                AliyunOSSResumePhotoStorage(settings)
                if settings.aliyun_oss_configured
                else UnavailableResumePhotoStorage()
            )
            with PostgresDatabase(settings.database_url, id_generator) as database:
                auth_repository = PostgresAuthRepository(database)
                auth_store = RedisAuthStore(settings)
                app_instance.state.auth_service = AuthApplicationService(
                    repository=auth_repository,
                    auth_store=auth_store,
                    email_sender=SmtpEmailSender(settings),
                    settings=settings,
                )
                resume_repository = PostgresResumeRepository(database)
                conversation_store = PostgresConversationStore(database)
                message_store = PostgresMessageStore(database)
                run_store = PostgresRunStore(database)
                task_result_store = PostgresTaskResultStore(database)
                event_store = RedisAgentEventStore(settings)
                agent_task_queue = CeleryAgentTaskQueue()

                def create_postgres_runner(
                    agent: AgentType,
                    graph: Any | None = None,
                    attachment_store: Any | None = None,
                ) -> AgentRunner:
                    """使用当前 PostgreSQL 运行时组装智能体 Runner。"""
                    return build_agent_runner(
                        settings=settings,
                        checkpointer=checkpointer,
                        run_store=run_store,
                        run_lock=PostgresRunLock(database),
                        conversation_store=conversation_store,
                        message_store=message_store,
                        event_sequence=MemoryEventSequence(),
                        model_provider=model_provider,
                        graph=graph,
                        agent=agent,
                        task_result_store=task_result_store,
                        attachment_store=attachment_store,
                        id_generator=id_generator,
                        cancel_signal=event_store,
                        max_question_rounds=(
                            JOB_AGENT_MAX_QUESTION_ROUNDS_PER_RUN
                            if agent == JOB_AGENT
                            else MAX_QUESTION_ROUNDS_PER_RUN
                        ),
                    )

                runner = create_postgres_runner(COMMON_AGENT)
                resolved_model_provider = model_provider or OpenAICompatibleProvider(settings)
                basic_conversation_agent = create_basic_conversation_agent(
                    agent=BASE_CONVERSATION_AGENT,
                    chat_model=resolved_model_provider.create_chat_model(),
                    checkpointer=checkpointer,
                )
                basic_conversation_runner = create_postgres_runner(
                    agent=BASE_CONVERSATION_AGENT,
                    graph=basic_conversation_agent.compiled_graph,
                )
                job_resume_reader = SavedJobResumeReader(resume_repository)
                job_agent = create_job_agent(
                    agent=JOB_AGENT,
                    chat_model=resolved_model_provider.create_chat_model(),
                    checkpointer=checkpointer,
                    resume_reader=job_resume_reader.read,
                    resume_optimization_writer=job_resume_reader.apply_optimization,
                )
                job_runner = create_postgres_runner(
                    agent=JOB_AGENT,
                    graph=job_agent.compiled_graph,
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
                    agent=IMAGE_AGENT,
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
                    agent=LISTING_AGENT,
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
                    agent=RESEARCH_AGENT,
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
                    agent=LABOR_LAW_AGENT,
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
                    agent=LITERATURE_READER_AGENT,
                    graph=literature_graph,
                )
                _install_runtime_state(
                    app_instance,
                    settings,
                    {
                        COMMON_AGENT: runner,
                        BASE_CONVERSATION_AGENT: basic_conversation_runner,
                        IMAGE_AGENT: image_runner,
                        LISTING_AGENT: listing_runner,
                        RESEARCH_AGENT: research_runner,
                        LABOR_LAW_AGENT: labor_law_runner,
                        LITERATURE_READER_AGENT: literature_runner,
                        JOB_AGENT: job_runner,
                    },
                    MemoryEventSequence(),
                    conversation_store,
                    message_store,
                    task_result_store,
                    image_storage,
                    event_store,
                    agent_task_queue,
                    run_store,
                )
                app_instance.state.literature_service = LiteratureApplicationService(
                    repository=literature_repository,
                    storage=literature_storage,
                    task_queue=CeleryLiteratureTaskQueue(),
                    chat_service=app_instance.state.agent_registry.get_service(
                        LITERATURE_READER_AGENT
                    ),
                    settings=settings,
                    id_generator=id_generator,
                )
                app_instance.state.resume_service = ResumeApplicationService(
                    repository=resume_repository,
                    photo_storage=resume_photo_storage,
                    pdf_renderer=PlaywrightResumePdfRenderer(settings),
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
                    await event_store.aclose()
                    auth_store.close()

    return lifespan


def _install_runtime_state(
    app_instance: FastAPI,
    settings: AppSettings,
    runners: dict[AgentType, Any],
    event_sequence: Any,
    conversation_store: PostgresConversationStore,
    message_store: PostgresMessageStore,
    task_result_store: PostgresTaskResultStore,
    attachment_store: Any,
    event_store: RedisAgentEventStore,
    agent_task_queue: CeleryAgentTaskQueue,
    run_store: PostgresRunStore,
) -> None:
    """组装注册表、共享事件发布器和查询服务。"""
    publisher = EventPublisher(event_sequence, settings.sse_heartbeat_seconds)
    services = {
        agent: AgentApplicationService(
            runner,
            publisher,
            conversation_store=conversation_store,
            run_store=run_store,
            event_store=event_store,
            task_queue=agent_task_queue,
        )
        for agent, runner in runners.items()
    }
    registry = AgentRegistry(PROJECT_AGENT_DEFINITIONS, services)
    app_instance.state.settings = settings
    app_instance.state.agent_event_store = event_store
    app_instance.state.agent_task_queue = agent_task_queue
    app_instance.state.agent_registry = registry
    app_instance.state.agent_session_service = AgentSessionApplicationService(
        conversation_store=conversation_store,
        run_store=run_store,
        event_store=event_store,
        agent_services={agent.value: service for agent, service in services.items()},
    )
    app_instance.state.task_result_store = task_result_store
    task_result_service = TaskResultApplicationService(task_result_store)
    app_instance.state.task_result_service = task_result_service
    app_instance.state.research_service = ResearchApplicationService(
        services[RESEARCH_AGENT],
        task_result_service,
    )
    app_instance.state.attachment_store = attachment_store
    app_instance.state.conversation_service = ConversationApplicationService(
        conversation_store,
        message_store,
        task_result_store,
        attachment_store,
    )
