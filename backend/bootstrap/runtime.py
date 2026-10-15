"""应用运行时组装入口，负责装配依赖并管理资源生命周期。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agent.constants import COMMON_AGENT_ID, IMAGE_AGENT_ID, LISTING_AGENT_ID
from agent.persistence.memory import MemoryEventSequence
from agent.runner import AgentRunner, build_agent_runner
from agent.streaming.publisher import EventPublisher
from agents.definition import AgentDefinition
from agents.image_agent.constants import IMAGE_AGENT_DESCRIPTION, IMAGE_AGENT_NAME
from agents.image_agent.graph import build_image_agent_graph
from agents.image_agent.providers.result_downloader import ImageResultDownloader
from agents.image_agent.providers.tokenhub_client import TokenHubImageClient
from agents.listing_agent.constants import LISTING_AGENT_DESCRIPTION, LISTING_AGENT_NAME
from agents.listing_agent.graph import build_listing_agent_graph
from agents.registry import (
    COMMON_AGENT_DESCRIPTION,
    COMMON_AGENT_NAME,
    AgentRegistry,
)
from app.crud import (
    PostgresConversationStore,
    PostgresMessageStore,
    PostgresRunLock,
    PostgresRunStore,
    PostgresTaskResultStore,
)
from app.db.database import PostgresDatabase
from app.service.agent import AgentApplicationService
from app.service.conversation import ConversationApplicationService
from app.service.task_result import TaskResultApplicationService
from infra.aliyun_oss import AliyunOSSImageStorage
from infra.model_provider import ChatModelProvider, OpenAICompatibleProvider
from infra.object_storage import UnavailableImageObjectStore
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
                _install_runtime_state(
                    app_instance,
                    settings,
                    {
                        COMMON_AGENT_ID: runner,
                        IMAGE_AGENT_ID: image_runner,
                        LISTING_AGENT_ID: listing_runner,
                    },
                    MemoryEventSequence(),
                    conversation_store,
                    message_store,
                    task_result_store,
                    image_storage,
                )
                yield

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
    registry = AgentRegistry(
        [
            AgentDefinition(
                agent_id=COMMON_AGENT_ID,
                name=COMMON_AGENT_NAME,
                description=COMMON_AGENT_DESCRIPTION,
                supports_image_upload=False,
            ),
            AgentDefinition(
                agent_id=IMAGE_AGENT_ID,
                name=IMAGE_AGENT_NAME,
                description=IMAGE_AGENT_DESCRIPTION,
                supports_image_upload=True,
            ),
            AgentDefinition(
                agent_id=LISTING_AGENT_ID,
                name=LISTING_AGENT_NAME,
                description=LISTING_AGENT_DESCRIPTION,
                supports_image_upload=True,
            ),
        ],
        services,
    )
    app_instance.state.settings = settings
    app_instance.state.agent_registry = registry
    app_instance.state.agent_runner = runners[COMMON_AGENT_ID]
    app_instance.state.agent_service = services[COMMON_AGENT_ID]
    app_instance.state.task_result_store = task_result_store
    app_instance.state.task_result_service = TaskResultApplicationService(task_result_store)
    app_instance.state.attachment_store = attachment_store
    app_instance.state.conversation_service = ConversationApplicationService(
        conversation_store,
        message_store,
        task_result_store,
    )
