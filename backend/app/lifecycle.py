"""应用运行时组装与资源生命周期管理。"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from agent.persistence.memory import MemoryEventSequence
from agent.runner import AgentRunner, build_agent_runner
from agent.streaming.publisher import EventPublisher
from agents.definition import AgentDefinition
from agents.image_generation.constants import IMAGE_AGENT_DESCRIPTION, IMAGE_AGENT_NAME
from agents.image_generation.graph import build_image_agent_graph
from agents.image_generation.providers.result_downloader import ImageResultDownloader
from agents.image_generation.providers.tokenhub_client import TokenHubImageClient
from agents.registry import (
    DEFAULT_AGENT_DESCRIPTION,
    DEFAULT_AGENT_ID,
    DEFAULT_AGENT_NAME,
    TAOBAO_IMAGE_AGENT_ID,
    AgentRegistry,
)
from app.crud.postgres import (
    PostgresConversationStore,
    PostgresMessageStore,
    PostgresRunLock,
    PostgresRunStore,
    PostgresRuntimeStore,
    PostgresTaskResultStore,
)
from app.service.agent import AgentApplicationService
from app.service.conversation import ConversationApplicationService
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
            with PostgresRuntimeStore(settings.database_url, id_generator) as runtime_store:
                conversation_store = PostgresConversationStore(runtime_store)
                message_store = PostgresMessageStore(runtime_store)
                task_result_store = PostgresTaskResultStore(runtime_store)

                def create_postgres_runner(
                    agent_id: str,
                    graph: Any | None = None,
                    attachment_store: Any | None = None,
                ) -> AgentRunner:
                    """使用当前 PostgreSQL 运行时组装智能体 Runner。"""
                    return build_agent_runner(
                        settings=settings,
                        checkpointer=checkpointer,
                        run_store=PostgresRunStore(runtime_store),
                        run_lock=PostgresRunLock(runtime_store),
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

                runner = create_postgres_runner(DEFAULT_AGENT_ID)
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
                    agent_id=TAOBAO_IMAGE_AGENT_ID,
                    graph=image_graph,
                    attachment_store=image_storage,
                )
                _install_runtime_state(
                    app_instance,
                    settings,
                    {
                        DEFAULT_AGENT_ID: runner,
                        TAOBAO_IMAGE_AGENT_ID: image_runner,
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
                agent_id=DEFAULT_AGENT_ID,
                name=DEFAULT_AGENT_NAME,
                description=DEFAULT_AGENT_DESCRIPTION,
                supports_image_upload=False,
            ),
            AgentDefinition(
                agent_id=TAOBAO_IMAGE_AGENT_ID,
                name=IMAGE_AGENT_NAME,
                description=IMAGE_AGENT_DESCRIPTION,
                supports_image_upload=True,
            ),
        ],
        services,
    )
    app_instance.state.settings = settings
    app_instance.state.agent_registry = registry
    app_instance.state.agent_runner = runners[DEFAULT_AGENT_ID]
    app_instance.state.agent_service = services[DEFAULT_AGENT_ID]
    app_instance.state.task_result_store = task_result_store
    app_instance.state.attachment_store = attachment_store
    app_instance.state.conversation_service = ConversationApplicationService(
        conversation_store,
        message_store,
        task_result_store,
    )
