"""Celery Agent Worker 任务入口。"""

import asyncio
import logging

from fastapi import FastAPI

from agent.schemas.run import RunStatus
from agent.streaming.events import AgentEvent, AgentEventType
from app.crud.run import PostgresRunStore
from app.db.database import PostgresDatabase
from bootstrap.runtime import build_lifespan
from infra.agent_event_store import RedisAgentEventStore
from infra.celery_app import celery_app
from infra.settings import AppSettings
from infra.snowflake import get_snowflake_generator

logger = logging.getLogger(__name__)


async def _execute_agent_run(agent: str, run_id: str) -> None:
    """在 Worker 独立运行时中重建共享 Agent Runtime 并消费事件。"""
    settings = AppSettings()
    # Worker 使用独立雪花号；必须和 API、文献 Worker 及其他 Agent Worker 实例不同。
    settings = settings.model_copy(update={"snowflake_worker_id": settings.agent_worker_snowflake_id})
    worker_app = FastAPI()
    lifespan = build_lifespan(settings, model_provider=None)
    async with lifespan(worker_app):
        service = worker_app.state.agent_registry.get_service(agent)
        await service.execute_worker(run_id)


async def _record_worker_start_failure(run_id: str, settings: AppSettings) -> None:
    """若 Worker 异常退出，在可用共享存储中补齐安全终止事件。"""
    if settings.database_url is None:
        return
    id_generator = get_snowflake_generator(settings.agent_worker_snowflake_id)
    event_store = RedisAgentEventStore(settings)
    try:
        with PostgresDatabase(settings.database_url, id_generator) as database:
            run_store = PostgresRunStore(database)
            record = run_store.get(run_id)
            if record is None:
                return
            terminal_type_by_status = {
                RunStatus.COMPLETED: AgentEventType.RUN_COMPLETED,
                RunStatus.CANCELLED: AgentEventType.RUN_CANCELLED,
                RunStatus.FAILED: AgentEventType.RUN_FAILED,
            }
            last_event_type = event_store.last_event_type(
                record.conversation_id,
                record.run_id,
            )
            if record.status in terminal_type_by_status:
                expected_terminal_type = terminal_type_by_status[record.status]
                if last_event_type in {
                    AgentEventType.RUN_COMPLETED,
                    AgentEventType.RUN_CANCELLED,
                    AgentEventType.RUN_FAILED,
                }:
                    return
                event_type = expected_terminal_type
            elif record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                status_by_terminal_type = {
                    AgentEventType.RUN_COMPLETED: RunStatus.COMPLETED,
                    AgentEventType.RUN_CANCELLED: RunStatus.CANCELLED,
                    AgentEventType.RUN_FAILED: RunStatus.FAILED,
                }
                if record.metadata.get("action") != "resume":
                    status_by_terminal_type[AgentEventType.QUESTION_REQUIRED] = RunStatus.WAITING
                persisted_status = status_by_terminal_type.get(last_event_type)
                if persisted_status is not None:
                    record.status = persisted_status
                    if persisted_status == RunStatus.FAILED:
                        record.metadata["error_summary"] = "智能体运行失败，请稍后重试"
                    run_store.save(record)
                    return
                event_type = AgentEventType.RUN_FAILED
            else:
                # waiting 需要问题数据才能继续交互，不能合成空的 question.required。
                return
            event = AgentEvent(
                event_id="",
                event_type=event_type,
                conversation_id=record.conversation_id,
                run_id=record.run_id,
                sequence=1,
                data=(
                    {
                        "code": "AGENT_WORKER_START_FAILED",
                        "message": "智能体暂时无法启动，请稍后重新提交",
                    }
                    if event_type == AgentEventType.RUN_FAILED
                    else {}
                ),
            )
            await asyncio.to_thread(event_store.append, event)
            if record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                record.status = RunStatus.FAILED
                record.metadata["error_summary"] = "智能体 Worker 初始化失败"
                run_store.save(record)
    finally:
        await event_store.aclose()


@celery_app.task(
    name="app.service.agent_tasks.execute_agent_run",
    ignore_result=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def execute_agent_run(agent: str, run_id: str) -> None:
    """执行已入库的运行；任务参数只包含 Agent 和稳定 run_id。"""
    logger.info("agent task started agent=%s run_id=%s", agent, run_id)
    try:
        asyncio.run(_execute_agent_run(agent, run_id))
    except Exception as error:
        logger.exception(
            "agent worker runtime failed agent=%s run_id=%s error_type=%s",
            agent,
            run_id,
            type(error).__name__,
        )
        try:
            asyncio.run(_record_worker_start_failure(run_id, AppSettings()))
        except Exception as recovery_error:
            logger.error(
                "agent worker failure recovery unavailable run_id=%s error_type=%s",
                run_id,
                type(recovery_error).__name__,
            )
