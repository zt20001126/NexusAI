"""传输层无关的单实例智能体运行器。"""

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from agent.errors import (
    ConversationAccessDeniedError,
    InvalidResumeAnswersError,
    RunBusyError,
    RunNotCancellableError,
    RunNotResumableError,
)
from agent.graph import build_agent_graph
from agent.persistence.interfaces import (
    AttachmentStore,
    ConversationStore,
    EventSequence,
    MessageStore,
    RunLock,
    RunStore,
    TaskDispatcher,
    TaskResultStore,
)
from agent.persistence.memory import (
    DisabledTaskDispatcher,
    MemoryCheckpointProvider,
    MemoryConversationStore,
    MemoryEventSequence,
    MemoryMessageStore,
    MemoryRunLock,
    MemoryRunStore,
    MemoryAttachmentStore,
    MemoryTaskResultStore,
)
from agent.persistence.postgres import (
    PostgresConversationStore,
    PostgresMessageStore,
    PostgresRunLock,
    PostgresRunStore,
    PostgresRuntimeStore,
    PostgresTaskResultStore,
)
from agent.title import (
    ConversationTitleGenerator,
    ModelConversationTitleGenerator,
    fallback_conversation_title,
)
from agent.schemas.run import RunRecord, RunStatus
from agent.schemas.task_result import TaskResultStatus
from agent.schemas.question import QuestionPayload
from agent.schemas.tool_result import ToolResult
from agent.streaming.events import AgentEvent, AgentEventType
from agent.tools.registry import PAUSE_TOOL_NAMES
from infra.model_provider import ChatModelProvider, OpenAICompatibleProvider
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator

logger = logging.getLogger(__name__)
STREAMING_RESPONSE_NODES = frozenset({"agent", "result"})


def _message_text(content: Any) -> str:
    """提取用户可见文本块，忽略图像等非文本消息内容。"""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    text_parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            text_parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            text_parts.append(item["text"])
    return "".join(text_parts)


class AgentRunner:
    """执行一个已注册智能体的图并生成稳定业务事件。"""

    def __init__(
        self,
        *,
        graph: Any,
        run_store: RunStore,
        run_lock: RunLock,
        conversation_store: ConversationStore,
        message_store: MessageStore,
        task_dispatcher: TaskDispatcher,
        event_sequence: EventSequence,
        max_steps: int,
        max_tool_calls: int,
        max_output_chars: int,
        run_timeout_seconds: int,
        agent_id: str = "default",
        task_result_store: TaskResultStore | None = None,
        attachment_store: AttachmentStore | None = None,
        title_generator: ConversationTitleGenerator | None = None,
        id_generator: SnowflakeIdGenerator | None = None,
    ) -> None:
        """注入单个智能体图和共享运行时基础设施。"""
        self._graph = graph
        self._agent_id = agent_id
        self._run_store = run_store
        self._run_lock = run_lock
        self._conversation_store = conversation_store
        self._message_store = message_store
        self._task_dispatcher = task_dispatcher
        self._event_sequence = event_sequence
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._max_output_chars = max_output_chars
        self._run_timeout_seconds = run_timeout_seconds
        self._task_result_store = task_result_store
        self._attachment_store = attachment_store
        self._title_generator = title_generator
        self._id_generator = id_generator or get_snowflake_generator()
        self._cancel_events: dict[str, asyncio.Event] = {}

    def stream_chat(
        self,
        *,
        message: str,
        conversation_id: str | None = None,
        principal_id: str = "local-development",
        attachment_ids: list[str] | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """启动一次运行，并将会话绑定到可信主体和智能体。"""
        resolved_id = conversation_id or self._id_generator.next_id_string()
        resolved_attachments = attachment_ids or []
        if resolved_attachments:
            if self._attachment_store is None:
                raise ValueError("当前智能体不支持图片附件")
            self._attachment_store.validate_staged(resolved_attachments, principal_id)
        conversation = self._conversation_store.get(resolved_id)
        if conversation is not None and (
            conversation.get("principal_id") != principal_id
            or conversation.get("agent_id", "default") != self._agent_id
        ):
            raise ConversationAccessDeniedError()
        self._conversation_store.save(
            resolved_id,
            {"principal_id": principal_id, "agent_id": self._agent_id},
        )
        title_source_message = message if conversation is None else None
        task_result_id = self._id_generator.next_id_string()
        record = RunRecord(
            run_id=self._id_generator.next_id_string(),
            conversation_id=resolved_id,
            principal_id=principal_id,
            status=RunStatus.RUNNING,
            metadata={
                "task_result_id": task_result_id,
                "attachment_ids": resolved_attachments,
            },
            agent_id=self._agent_id,
        )
        self._run_store.save(record)
        message_id = self._message_store.save(resolved_id, record.run_id, "user", message)
        if resolved_attachments:
            if self._attachment_store is None:
                raise ValueError("当前智能体不支持图片附件")
            self._attachment_store.bind_to_message(
                resolved_attachments,
                principal_id,
                resolved_id,
                message_id,
            )
        graph_input = {
            "messages": [HumanMessage(content=message)],
            "original_request": message,
            "resume_answers": {},
            "agent_id": self._agent_id,
            "principal_id": principal_id,
            "conversation_id": resolved_id,
            "run_id": record.run_id,
            "task_result_id": task_result_id,
            "attachment_ids": resolved_attachments,
        }
        return self._stream_graph(
            record=record,
            graph_input=graph_input,
            title_source_message=title_source_message,
        )

    def resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str = "local-development",
    ) -> AsyncIterator[AgentEvent]:
        """校验等待状态和问题标识后，从相同 Checkpoint 恢复图。"""
        record = self._run_store.get(run_id)
        if (
            record is None
            or record.status != RunStatus.WAITING
            or record.conversation_id != conversation_id
            or record.principal_id != principal_id
            or record.agent_id != self._agent_id
        ):
            raise RunNotResumableError()
        pending_question_ids = set(record.metadata.get("pending_question_ids", []))
        if not pending_question_ids or set(answers) != pending_question_ids:
            raise InvalidResumeAnswersError()
        record.status = RunStatus.RUNNING
        self._run_store.save(record)
        answer_text = "\n".join(
            f"{question_id}: {', '.join(value) if isinstance(value, list) else value}"
            for question_id, value in answers.items()
        )
        self._message_store.save(
            conversation_id,
            record.run_id,
            "user",
            answer_text,
        )
        graph_input = {
            "messages": [HumanMessage(content=json.dumps(answers, ensure_ascii=False))],
            "resume_answers": answers,
            "agent_id": self._agent_id,
            "principal_id": principal_id,
            "conversation_id": conversation_id,
            "run_id": record.run_id,
            "task_result_id": record.metadata.get("task_result_id"),
            "attachment_ids": record.metadata.get("attachment_ids", []),
        }
        return self._stream_graph(record=record, graph_input=graph_input)

    def cancel(self, *, run_id: str, principal_id: str) -> None:
        """校验运行归属和状态后，立即设置进程内取消信号。"""
        record = self._run_store.get(run_id)
        if (
            record is None
            or record.principal_id != principal_id
            or record.status != RunStatus.RUNNING
        ):
            raise RunNotCancellableError()
        self._cancel_events.setdefault(run_id, asyncio.Event()).set()

    def submit_task(self, task_name: str, payload: dict[str, Any]) -> str:
        """通过可替换任务适配器提交长耗时工作。"""
        return self._task_dispatcher.submit(task_name, payload)

    async def _stream_graph(
        self,
        *,
        record: RunRecord,
        graph_input: dict[str, Any],
        title_source_message: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """执行此实例绑定的智能体图并映射为稳定事件。"""
        scope_key = self._scope_key(record)
        lock_acquired = False
        waiting_for_answer = False
        tool_call_count = 0
        output_char_count = 0
        streamed_text_by_node: dict[str, str] = {}
        cancel_event = self._cancel_events.setdefault(record.run_id, asyncio.Event())
        title_task: asyncio.Task[str | None] | None = None
        try:
            await self._run_lock.acquire(scope_key)
            lock_acquired = True
            if title_source_message is not None and self._title_generator is not None:
                # 首轮标题调用在后台并行执行，不阻塞智能体开始输出。
                title_task = asyncio.create_task(
                    self._title_generator.generate_title(title_source_message)
                )
            yield self._event(record, AgentEventType.RUN_STARTED)
            config = {
                "configurable": {"thread_id": scope_key},
                "recursion_limit": self._max_steps,
            }
            async with asyncio.timeout(self._run_timeout_seconds):
                graph_stream = self._graph.astream(
                    graph_input,
                    config=config,
                    stream_mode=["messages", "updates"],
                )
                async for stream_item in self._cancel_aware_stream(graph_stream, cancel_event):
                    if stream_item is None:
                        record.status = RunStatus.CANCELLED
                        yield self._event(record, AgentEventType.RUN_CANCELLED)
                        return
                    stream_mode, payload = stream_item
                    if stream_mode == "messages":
                        message, metadata = payload
                        node_name = metadata.get("langgraph_node")
                        content = _message_text(message.content) if isinstance(
                            message, (AIMessage, AIMessageChunk)
                        ) else ""
                        if node_name in STREAMING_RESPONSE_NODES and content:
                            output_char_count += len(content)
                            if output_char_count > self._max_output_chars:
                                record.status = RunStatus.FAILED
                                yield self._event(
                                    record,
                                    AgentEventType.RUN_FAILED,
                                    {"code": "AGENT_OUTPUT_LIMIT", "message": "智能体输出超过允许长度"},
                                )
                                return
                            yield self._event(
                                record,
                                AgentEventType.MESSAGE_DELTA,
                                {"content": content},
                            )
                            streamed_text_by_node[node_name] = (
                                streamed_text_by_node.get(node_name, "") + content
                            )
                        continue
                    for node_name, node_update in payload.items():
                        if not isinstance(node_update, dict):
                            continue
                        for message in node_update.get("messages", []):
                            async for event in self._events_for_message(record, message):
                                if (
                                    event.event_type == AgentEventType.MESSAGE_COMPLETED
                                    and isinstance(event.data.get("content"), str)
                                ):
                                    completed_content = event.data["content"]
                                    streamed_content = streamed_text_by_node.pop(node_name, "")
                                    if completed_content.startswith(streamed_content):
                                        missing_content = completed_content[len(streamed_content):]
                                    else:
                                        missing_content = completed_content
                                    if missing_content:
                                        output_char_count += len(missing_content)
                                        if output_char_count > self._max_output_chars:
                                            record.status = RunStatus.FAILED
                                            yield self._event(
                                                record,
                                                AgentEventType.RUN_FAILED,
                                                {"code": "AGENT_OUTPUT_LIMIT", "message": "智能体输出超过允许长度"},
                                            )
                                            return
                                        yield self._event(
                                            record,
                                            AgentEventType.MESSAGE_DELTA,
                                            {"content": missing_content},
                                        )
                                if event.event_type == AgentEventType.TOOL_STARTED:
                                    tool_call_count += 1
                                    if tool_call_count > self._max_tool_calls:
                                        record.status = RunStatus.FAILED
                                        yield self._event(
                                            record,
                                            AgentEventType.RUN_FAILED,
                                            {"code": "AGENT_TOOL_CALL_LIMIT", "message": "工具调用次数超过允许范围"},
                                        )
                                        return
                                if event.event_type == AgentEventType.QUESTION_REQUIRED:
                                    waiting_for_answer = True
                                    record.metadata["pending_question_ids"] = [
                                        item["id"]
                                        for item in event.data.get("questions", [])
                                        if isinstance(item, dict) and isinstance(item.get("id"), str)
                                    ]
                                yield event
                                if event.event_type == AgentEventType.RUN_FAILED:
                                    record.status = RunStatus.FAILED
                                    return
            if waiting_for_answer:
                record.status = RunStatus.WAITING
            else:
                record.status = RunStatus.COMPLETED
                yield self._event(record, AgentEventType.RUN_COMPLETED)
        except RunBusyError:
            record.status = RunStatus.FAILED
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "RUN_BUSY", "message": "当前会话正在处理中"},
            )
        except GraphRecursionError:
            record.status = RunStatus.FAILED
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "AGENT_MAX_STEPS", "message": "智能体执行步骤超过允许范围"},
            )
        except TimeoutError:
            record.status = RunStatus.FAILED
            logger.warning(
                "智能体运行超时 conversation_id=%s run_id=%s",
                record.conversation_id,
                record.run_id,
            )
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "AGENT_RUN_TIMEOUT", "message": "智能体运行超时，请稍后重试"},
            )
        except asyncio.CancelledError:
            # 客户端断开时保存取消状态并继续抛出，避免伪造无法送达的终止事件。
            record.status = RunStatus.CANCELLED
            raise
        except Exception:
            record.status = RunStatus.FAILED
            logger.exception(
                "智能体运行失败 conversation_id=%s run_id=%s",
                record.conversation_id,
                record.run_id,
            )
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "AGENT_RUN_FAILED", "message": "智能体运行失败，请稍后重试"},
            )
        finally:
            try:
                if title_task is not None and title_source_message is not None:
                    await self._persist_conversation_title(
                        title_task,
                        record.conversation_id,
                        title_source_message,
                    )
                task_result_id = record.metadata.get("task_result_id")
                if isinstance(task_result_id, str) and self._task_result_store is not None:
                    try:
                        if record.status == RunStatus.CANCELLED:
                            self._task_result_store.set_status(
                                task_result_id,
                                record.principal_id,
                                TaskResultStatus.CANCELLED,
                            )
                        elif record.status == RunStatus.FAILED:
                            self._task_result_store.set_status(
                                task_result_id,
                                record.principal_id,
                                TaskResultStatus.FAILED,
                            )
                    except Exception:
                        logger.exception(
                            "任务结果终态写入失败 task_result_id=%s",
                            task_result_id,
                        )
                self._run_store.save(record)
            finally:
                try:
                    if lock_acquired:
                        self._run_lock.release(scope_key)
                finally:
                    self._cancel_events.pop(record.run_id, None)

    async def _persist_conversation_title(
        self,
        title_task: asyncio.Task[str | None],
        conversation_id: str,
        first_user_message: str,
    ) -> None:
        """等待并持久化首轮标题；模型异常时回退且不影响对话结果。"""
        try:
            generated_title = await title_task
        except asyncio.CancelledError:
            generated_title = None
        except Exception:
            logger.exception(
                "会话标题生成任务失败 conversation_id=%s",
                conversation_id,
            )
            generated_title = None

        title = generated_title or fallback_conversation_title(first_user_message)
        try:
            self._conversation_store.set_title_if_empty(
                conversation_id,
                title,
            )
        except Exception:
            logger.exception("会话标题保存失败 conversation_id=%s", conversation_id)

    @staticmethod
    async def _cancel_aware_stream(
        stream: AsyncIterator[tuple[str, Any]],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, Any] | None]:
        """同时等待图更新与取消信号，避免长节点阻塞取消。"""
        next_item: asyncio.Task[tuple[str, Any]] | None = None
        cancelled: asyncio.Task[bool] | None = None
        try:
            while True:
                next_item = asyncio.create_task(anext(stream))
                cancelled = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    {next_item, cancelled}, return_when=asyncio.FIRST_COMPLETED
                )
                if cancelled in done:
                    next_item.cancel()
                    with suppress(asyncio.CancelledError, StopAsyncIteration):
                        await next_item
                    next_item = None
                    cancelled = None
                    yield None
                    return
                cancelled.cancel()
                with suppress(asyncio.CancelledError):
                    await cancelled
                cancelled = None
                try:
                    yield next_item.result()
                except StopAsyncIteration:
                    return
                finally:
                    next_item = None
        finally:
            for task in (next_item, cancelled):
                if task is not None and not task.done():
                    task.cancel()
                    with suppress(asyncio.CancelledError, StopAsyncIteration):
                        await task
            with suppress(Exception):
                await stream.aclose()

    async def _events_for_message(
        self, record: RunRecord, message: Any
    ) -> AsyncIterator[AgentEvent]:
        """把 LangChain 消息转换为受控工具、追问或文本事件。"""
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                yield self._event(
                    record,
                    AgentEventType.TOOL_STARTED,
                    {"tool_name": tool_call.get("name", "")},
                )
            if isinstance(message.content, str) and message.content:
                message_id = self._message_store.save(
                    record.conversation_id,
                    record.run_id,
                    "assistant",
                    message.content,
                )
                task_result_id = record.metadata.get("task_result_id")
                if isinstance(task_result_id, str) and self._task_result_store is not None:
                    self._task_result_store.link_message(
                        task_result_id,
                        message_id,
                        record.principal_id,
                    )
                yield self._event(
                    record,
                    AgentEventType.MESSAGE_COMPLETED,
                    {"content": message.content},
                )
            return
        if not isinstance(message, ToolMessage):
            return
        payload = self._safe_tool_payload(message.content)
        if message.name in PAUSE_TOOL_NAMES:
            if not payload.get("success", False):
                yield self._event(
                    record,
                    AgentEventType.RUN_FAILED,
                    {"code": "QUESTION_TOOL_FAILED", "message": "生成追问信息失败"},
                )
                return
            try:
                questions = QuestionPayload.model_validate(payload.get("data", {}))
            except ValueError:
                yield self._event(
                    record,
                    AgentEventType.RUN_FAILED,
                    {"code": "INVALID_QUESTION_PAYLOAD", "message": "追问信息格式不正确"},
                )
                return
            question_message_id = self._message_store.save(
                record.conversation_id,
                record.run_id,
                "assistant",
                "\n".join(
                    f"{question.title}\n{question.prompt}"
                    for question in questions.questions
                ),
            )
            task_result = payload.get("data", {}).get("task_result")
            if (
                isinstance(task_result, dict)
                and isinstance(task_result.get("task_result_id"), str)
                and self._task_result_store is not None
            ):
                self._task_result_store.link_message(
                    task_result["task_result_id"],
                    question_message_id,
                    record.principal_id,
                )
            yield self._event(
                record,
                AgentEventType.QUESTION_REQUIRED,
                questions.model_dump(),
            )
            if isinstance(task_result, dict):
                yield self._event(
                    record,
                    AgentEventType.TASK_RESULT_UPDATED,
                    task_result,
                )
            return
        yield self._event(
            record,
            AgentEventType.TOOL_COMPLETED,
            {
                "tool_name": message.name or "unknown",
                "success": bool(payload.get("success", False)),
                "data": payload.get("data", {}),
            },
        )
        if message.name == "generate_image":
            task_result = payload.get("data", {}).get("task_result")
            if isinstance(task_result, dict):
                yield self._event(
                    record,
                    AgentEventType.TASK_RESULT_UPDATED,
                    task_result,
                )

    @staticmethod
    def _safe_tool_payload(content: Any) -> dict[str, Any]:
        """校验有界工具结果，畸形结果降级为稳定失败结构。"""
        raw_content = str(content)
        if len(raw_content) > 64_000:
            return {"success": False, "data": {}, "code": "INVALID_TOOL_RESULT"}
        try:
            return ToolResult.model_validate_json(raw_content).model_dump()
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"success": False, "data": {}, "code": "INVALID_TOOL_RESULT"}

    def _event(
        self,
        record: RunRecord,
        event_type: AgentEventType,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """生成内部有序事件；发布器会在实际交付前重分配游标。"""
        sequence = self._event_sequence.next(record.conversation_id)
        return AgentEvent(
            event_id=f"{record.conversation_id}:{sequence}",
            event_type=event_type,
            conversation_id=record.conversation_id,
            run_id=record.run_id,
            sequence=sequence,
            data=data or {},
        )

    @staticmethod
    def _scope_key(record: RunRecord) -> str:
        """用可信主体隔离锁和 Checkpoint 内部键。"""
        return f"{record.principal_id}:{record.agent_id}:{record.conversation_id}"


def build_memory_runner(
    settings: AppSettings,
    graph: Any | None = None,
    model_provider: ChatModelProvider | None = None,
    *,
    conversation_store: ConversationStore | None = None,
    message_store: MessageStore | None = None,
    agent_id: str = "default",
    task_result_store: TaskResultStore | None = None,
    attachment_store: AttachmentStore | None = None,
    title_generator: ConversationTitleGenerator | None = None,
) -> AgentRunner:
    """创建供测试显式使用的内存运行器，不参与应用默认启动流程。"""
    checkpointer = MemoryCheckpointProvider().get_checkpointer()
    return _build_runner(
        settings=settings,
        checkpointer=checkpointer,
        run_store=MemoryRunStore(),
        run_lock=MemoryRunLock(),
        conversation_store=conversation_store or MemoryConversationStore(),
        message_store=message_store or MemoryMessageStore(),
        event_sequence=MemoryEventSequence(),
        model_provider=model_provider,
        graph=graph,
        agent_id=agent_id,
        task_result_store=task_result_store or MemoryTaskResultStore(),
        attachment_store=attachment_store or MemoryAttachmentStore(),
        title_generator=title_generator,
        id_generator=get_snowflake_generator(settings.snowflake_worker_id),
    )


def build_postgres_runner(
    settings: AppSettings,
    *,
    checkpointer: Any,
    runtime_store: PostgresRuntimeStore,
    model_provider: ChatModelProvider | None = None,
    graph: Any | None = None,
    agent_id: str = "default",
    attachment_store: AttachmentStore | None = None,
    title_generator: ConversationTitleGenerator | None = None,
) -> AgentRunner:
    """创建 PostgreSQL 持久化运行器，保留仅用于执行协调的进程内锁。"""
    return _build_runner(
        settings=settings,
        checkpointer=checkpointer,
        run_store=PostgresRunStore(runtime_store),
        run_lock=PostgresRunLock(runtime_store),
        conversation_store=PostgresConversationStore(runtime_store),
        message_store=PostgresMessageStore(runtime_store),
        event_sequence=MemoryEventSequence(),
        model_provider=model_provider,
        graph=graph,
        agent_id=agent_id,
        task_result_store=PostgresTaskResultStore(runtime_store),
        attachment_store=attachment_store,
        title_generator=title_generator,
        id_generator=get_snowflake_generator(settings.snowflake_worker_id),
    )


def _build_runner(
    *,
    settings: AppSettings,
    checkpointer: Any,
    run_store: RunStore,
    run_lock: RunLock,
    conversation_store: ConversationStore,
    message_store: MessageStore,
    event_sequence: EventSequence,
    model_provider: ChatModelProvider | None = None,
    graph: Any | None = None,
    agent_id: str = "default",
    task_result_store: TaskResultStore | None = None,
    attachment_store: AttachmentStore | None = None,
    title_generator: ConversationTitleGenerator | None = None,
    id_generator: SnowflakeIdGenerator | None = None,
) -> AgentRunner:
    """为一个 agent_id 组装图和可替换运行基础设施。"""
    provider = model_provider or OpenAICompatibleProvider(settings)
    if graph is None:
        graph = build_agent_graph(checkpointer, provider.create_chat_model())
    resolved_title_generator = title_generator or ModelConversationTitleGenerator(
        provider,
        settings.conversation_title_timeout_seconds,
    )
    return AgentRunner(
        graph=graph,
        agent_id=agent_id,
        task_result_store=task_result_store,
        attachment_store=attachment_store,
        title_generator=resolved_title_generator,
        id_generator=id_generator,
        run_store=run_store,
        run_lock=run_lock,
        conversation_store=conversation_store,
        message_store=message_store,
        task_dispatcher=DisabledTaskDispatcher(),
        event_sequence=event_sequence,
        max_steps=settings.agent_max_steps,
        max_tool_calls=settings.agent_max_tool_calls,
        max_output_chars=settings.agent_max_output_chars,
        run_timeout_seconds=settings.agent_run_timeout_seconds,
    )
