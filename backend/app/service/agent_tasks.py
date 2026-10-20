"""Celery Agent Worker 任务入口。"""

import asyncio
import logging

from fastapi import FastAPI

from agent.constants import MAX_QUESTION_ROUNDS_PER_RUN
from agent.schemas.run import RunStatus
from agent.streaming.events import (
    AgentEvent,
    AgentEventType,
    RunTerminalStatus,
    get_run_terminal_status,
)
from app.crud.run import PostgresRunStore
from app.crud.message import PostgresMessageStore
from app.crud.task_result import PostgresTaskResultStore
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
            if record.status == RunStatus.WAITING:
                if get_run_terminal_status(
                    event_store.last_event(record.conversation_id, record.run_id)
                ) == RunTerminalStatus.WAITING:
                    return
                message_store = PostgresMessageStore(database)
                messages = message_store.list_by_conversation(record.conversation_id, 100, None)
                question_message = next(
                    (
                        message
                        for message in messages
                        if message.role == "assistant"
                        and any(
                            isinstance(block, dict)
                            and block.get("type") == "question"
                            and block.get("run_id") == record.run_id
                            for block in message.content.get("blocks", [])
                        )
                    ),
                    None,
                )
                if question_message is None:
                    questions = record.metadata.get("pending_questions")
                    if not isinstance(questions, list) or not questions:
                        return
                    message_id = id_generator.next_id_string()
                    question_round = record.metadata.get("question_round_count", 1)
                    blocks = [
                        {
                            "id": id_generator.next_id_string(),
                            "type": "text",
                            "text": "\n".join(
                                item.get("title", "")
                                for item in questions
                                if isinstance(item, dict)
                            ),
                        },
                        {
                            "id": id_generator.next_id_string(),
                            "type": "question",
                            "run_id": record.run_id,
                            "question_round": question_round,
                            "max_question_rounds": MAX_QUESTION_ROUNDS_PER_RUN,
                            "questions": questions,
                        },
                    ]
                    content = {"blocks": blocks}
                    message_store.save(
                        record.conversation_id,
                        "assistant",
                        content,
                        message_id=message_id,
                    )
                    if record.metadata.get("task_result_id"):
                        PostgresTaskResultStore(database).link_message(
                            str(record.metadata["task_result_id"]),
                            message_id,
                            record.principal_id,
                        )
                    question_message = message_store.get_for_conversation(
                        record.conversation_id, message_id
                    )
                if question_message is None:
                    return
                last_event = event_store.last_event(record.conversation_id, record.run_id)
                if not (
                    last_event is not None
                    and last_event.event_type == AgentEventType.MESSAGE
                    and last_event.data.get("operation") == "snapshot"
                    and last_event.data.get("message_id") == question_message.message_id
                ):
                    await asyncio.to_thread(
                        event_store.append,
                        AgentEvent(
                            event_id="",
                            event_type=AgentEventType.MESSAGE,
                            conversation_id=record.conversation_id,
                            run_id=record.run_id,
                            sequence=0,
                            data={
                                "operation": "snapshot",
                                "message_id": question_message.message_id,
                                "content": question_message.content,
                            },
                        ),
                    )
                last_event = event_store.last_event(record.conversation_id, record.run_id)
                if (
                    last_event is None
                    or get_run_terminal_status(last_event) != RunTerminalStatus.WAITING
                ):
                    await asyncio.to_thread(
                        event_store.append,
                        AgentEvent(
                            event_id="",
                            event_type=AgentEventType.END,
                            conversation_id=record.conversation_id,
                            run_id=record.run_id,
                            sequence=0,
                            data={"status": RunTerminalStatus.WAITING.value},
                        ),
                    )
                return
            terminal_status_by_run_status = {
                RunStatus.COMPLETED: RunTerminalStatus.COMPLETED,
                RunStatus.CANCELLED: RunTerminalStatus.CANCELLED,
                RunStatus.FAILED: RunTerminalStatus.FAILED,
            }
            last_event = event_store.last_event(
                record.conversation_id,
                record.run_id,
            )
            if record.status in terminal_status_by_run_status:
                terminal_status = terminal_status_by_run_status[record.status]
                if (
                    last_event is not None
                    and last_event.event_type == AgentEventType.END
                    and get_run_terminal_status(last_event) == terminal_status
                ):
                    return
                event_data = {"status": terminal_status.value}
                if terminal_status == RunTerminalStatus.FAILED:
                    event_data.update(
                        {
                            "code": "AGENT_WORKER_START_FAILED",
                            "message": "智能体暂时无法启动，请稍后重新提交",
                        }
                    )
            elif record.status in {RunStatus.QUEUED, RunStatus.RUNNING}:
                run_status_by_terminal_status = {
                    RunTerminalStatus.COMPLETED: RunStatus.COMPLETED,
                    RunTerminalStatus.CANCELLED: RunStatus.CANCELLED,
                    RunTerminalStatus.FAILED: RunStatus.FAILED,
                }
                if record.metadata.get("action") != "resume":
                    if (
                        last_event is not None
                        and last_event.event_type == AgentEventType.END
                        and get_run_terminal_status(last_event) == RunTerminalStatus.WAITING
                    ):
                        record.status = RunStatus.WAITING
                        run_store.save(record)
                        return
                persisted_terminal_status = (
                    get_run_terminal_status(last_event)
                    if last_event is not None
                    else None
                )
                persisted_status = run_status_by_terminal_status.get(
                    persisted_terminal_status
                )
                if persisted_status is not None:
                    record.status = persisted_status
                    if persisted_status == RunStatus.FAILED:
                        record.metadata["error_summary"] = "智能体运行失败，请稍后重试"
                    run_store.save(record)
                    return
                terminal_status = RunTerminalStatus.FAILED
                event_data = {
                    "status": terminal_status.value,
                    "code": "AGENT_WORKER_START_FAILED",
                    "message": "智能体暂时无法启动，请稍后重新提交",
                }
            else:
                # waiting 需要问题数据才能继续交互，不能合成空的题卡快照。
                return
            event = AgentEvent(
                event_id="",
                event_type=AgentEventType.END,
                conversation_id=record.conversation_id,
                run_id=record.run_id,
                sequence=1,
                data={
                    "status": event_data["status"],
                    **(
                        {
                            "error": {
                                "code": event_data["code"],
                                "message": event_data["message"],
                            }
                        }
                        if event_data["status"] == RunTerminalStatus.FAILED.value
                        else {}
                    ),
                },
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
