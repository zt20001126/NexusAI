"""传输层无关的单实例智能体运行器。"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import suppress
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from agent.enums import AgentType
from agent.constants import (
    BASE_CONVERSATION_AGENT,
    CHECKPOINT_AGENT_NAMESPACE_COMPATIBILITY,
    COMMON_AGENT,
    LISTING_AGENT,
    MAX_QUESTION_ROUNDS_PER_RUN,
)
from agent.errors import (
    ConversationAccessDeniedError,
    InvalidResumeAnswersError,
    RunBusyError,
    RunNotCancellableError,
    RunNotResumableError,
    AgentRunRequestConflictError,
    AgentRunPreparationPendingError,
    DuplicateAgentRunRequest,
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
from agent.title import (
    ConversationTitleGenerator,
    ModelConversationTitleGenerator,
    fallback_conversation_title,
)
from agent.schemas.run import RunRecord, RunStatus
from agent.schemas.conversation import text_content
from agent.schemas.task_result import TaskResultStatus
from agent.schemas.question import QuestionPayload
from agent.schemas.tool_result import ToolResult
from agent.streaming.events import AgentEvent, AgentEventType
from agent.tools.registry import PAUSE_TOOL_NAMES
from infra.model_provider import ChatModelProvider, OpenAICompatibleProvider
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator, get_snowflake_generator

logger = logging.getLogger(__name__)
# 非流式节点完成后使用有界片段发送最终答复，避免单个 SSE 事件过大。
MESSAGE_DELTA_CHUNK_SIZE = 24
# 仅列出安全的面向用户模型节点；任务型智能体在结果安全后分段呈现用户文本。
STREAMING_RESPONSE_NODES_BY_AGENT = {
    COMMON_AGENT: frozenset({"agent", "result"}),
    BASE_CONVERSATION_AGENT: frozenset({"chat_node"}),
}


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


def _text_chunks(content: str) -> Iterator[str]:
    """将完成后的安全文本拆成有界片段，供 SSE 客户端逐段呈现。"""
    for index in range(0, len(content), MESSAGE_DELTA_CHUNK_SIZE):
        yield content[index : index + MESSAGE_DELTA_CHUNK_SIZE]


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
        agent: AgentType = COMMON_AGENT,
        task_result_store: TaskResultStore | None = None,
        attachment_store: AttachmentStore | None = None,
        title_generator: ConversationTitleGenerator | None = None,
        id_generator: SnowflakeIdGenerator | None = None,
        cancel_signal: Any | None = None,
    ) -> None:
        """注入单个智能体图和共享运行时基础设施。"""
        self._graph = graph
        self._agent = agent
        # 仅允许已确认面向用户的模型节点实时转发 token，避免暴露业务计划和结构化草稿。
        self._streaming_response_nodes = STREAMING_RESPONSE_NODES_BY_AGENT.get(
            agent,
            frozenset(),
        )
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
        self._cancel_signal = cancel_signal
        self._cancel_events: dict[str, asyncio.Event] = {}

    def stream_chat(
        self,
        *,
        message: str,
        conversation_id: str | None = None,
        principal_id: str = "local-development",
        attachment_ids: list[str] | None = None,
        graph_context: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """兼容同步流式调用；HTTP 后台任务通过 prepare_chat/execute_prepared 分段执行。"""
        record = self.prepare_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
            attachment_ids=attachment_ids,
            graph_context=graph_context,
            request_id=request_id,
        )
        return self.execute_prepared(record.run_id)

    def prepare_chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
        attachment_ids: list[str] | None = None,
        graph_context: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> RunRecord:
        """先保存用户输入和排队运行，供 Celery Worker 脱离 HTTP 连接执行。

        Step 1: 校验会话与附件所有权，并计算请求幂等摘要。
        Step 2: 创建或复用排队运行，保存已有消息表可读取的执行输入。
        Step 3: 返回稳定会话及运行标识，由应用服务派发后台任务。
        """
        resolved_id = conversation_id or self._id_generator.next_id_string()
        resolved_attachments = attachment_ids or []
        resolved_context = dict(graph_context or {})
        payload_hash = hashlib.sha256(json.dumps(
            {
                "agent": self._agent.value,
                "conversation_id": conversation_id,
                "message": message,
                "attachment_ids": resolved_attachments,
                "graph_context": resolved_context,
            },
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")).hexdigest()
        request_key = (
            hashlib.sha256(f"{principal_id}:{request_id}".encode("utf-8")).hexdigest()
            if request_id
            else None
        )
        if request_id:
            existing = self._run_store.get_by_request_id(request_id, principal_id)
            if existing is not None:
                if existing.metadata.get("request_hash") != payload_hash:
                    raise AgentRunRequestConflictError()
                for _ in range(40):
                    if existing.metadata.get("input_message_id"):
                        return existing
                    time.sleep(0.025)
                    existing = self._run_store.get_by_request_id(request_id, principal_id)
                    if existing is None:
                        break
                if existing is not None and existing.metadata.get("input_message_id"):
                    return existing
                raise AgentRunPreparationPendingError()
        if resolved_attachments:
            if self._attachment_store is None:
                raise ValueError("当前智能体不支持图片附件")
            self._attachment_store.validate_staged(resolved_attachments, principal_id)
        conversation = self._conversation_store.get(resolved_id)
        if conversation is not None and (
            conversation.get("principal_id") != principal_id
            or conversation.get("agent", COMMON_AGENT) != self._agent
        ):
            raise ConversationAccessDeniedError()
        self._conversation_store.save(
            resolved_id,
            {"principal_id": principal_id, "agent": self._agent},
        )
        task_result_id = self._id_generator.next_id_string()
        record = RunRecord(
            run_id=self._id_generator.next_id_string(),
            conversation_id=resolved_id,
            principal_id=principal_id,
            status=RunStatus.QUEUED,
            metadata={
                "task_result_id": task_result_id,
                "attachment_ids": resolved_attachments,
                "question_round_count": 0,
                "request_id": request_id,
                "request_key": request_key,
                "request_hash": payload_hash,
                "graph_context": resolved_context,
                "is_new_conversation": conversation is None,
            },
            agent=self._agent,
        )
        try:
            self._run_store.save(record)
        except DuplicateAgentRunRequest:
            existing = self._run_store.get_by_request_id(request_id or "", principal_id)
            if existing is None:
                raise
            if existing.metadata.get("request_hash") != payload_hash:
                raise AgentRunRequestConflictError() from None
            # 首个请求先写运行、再写消息；短暂等待它完成该小段数据库准备。
            for _ in range(40):
                if existing.metadata.get("input_message_id"):
                    return existing
                time.sleep(0.025)
                existing = self._run_store.get_by_request_id(request_id or "", principal_id)
                if existing is None:
                    break
            if existing is not None and existing.metadata.get("input_message_id"):
                return existing
            raise AgentRunPreparationPendingError() from None
        user_content = text_content(message)
        user_content["blocks"].extend(
            {"type": "image", "attachment_id": attachment_id}
            for attachment_id in resolved_attachments
        )
        message_id = self._message_store.save(resolved_id, "user", user_content)
        record.metadata["input_message_id"] = message_id
        self._run_store.save(record)
        if resolved_attachments:
            if self._attachment_store is None:
                raise ValueError("当前智能体不支持图片附件")
            self._attachment_store.bind_to_message(
                resolved_attachments,
                principal_id,
                resolved_id,
                message_id,
            )
        return record

    def execute_prepared(self, run_id: str) -> AsyncIterator[AgentEvent]:
        """从数据库中的排队记录和用户消息重建图输入并开始执行。"""
        return self._execute_prepared_events(run_id)

    async def _execute_prepared_events(self, run_id: str) -> AsyncIterator[AgentEvent]:
        """用 run 级共享锁排除重复投递，再声明运行并执行现有图。"""
        record = self._run_store.get(run_id)
        if record is None or record.agent != self._agent or record.status not in {
            RunStatus.QUEUED,
            RunStatus.RUNNING,
        }:
            return

        # 先持有 run 级锁再 claim，避免同一 request_id 的并发 Celery 投递
        # 在首个 Worker 写入会话锁前，把正常运行误判为中断。
        run_lock_key = f"agent-run:{run_id}"
        lock_acquired = False
        try:
            try:
                await self._run_lock.acquire(run_lock_key)
                lock_acquired = True
            except RunBusyError:
                return

            claim = getattr(self._run_store, "claim", None)
            if callable(claim) and not claim(run_id):
                record = self._run_store.get(run_id) or record
                if record.status != RunStatus.RUNNING:
                    return
                record.status = RunStatus.FAILED
                record.metadata["error_summary"] = "智能体 Worker 中断，本轮未能安全续跑"
                yield self._event(
                    record,
                    AgentEventType.RUN_FAILED,
                    {
                        "code": "AGENT_WORKER_INTERRUPTED",
                        "message": "本轮执行中断，请重新提交消息后重试",
                    },
                )
                return

            record = self._run_store.get(run_id) or record
            if record.metadata.get("action") == "resume":
                answers = record.metadata.get("resume_answers")
                if not isinstance(answers, dict):
                    record.status = RunStatus.FAILED
                    record.metadata["error_summary"] = "本轮输入暂时无法读取"
                    yield self._event(
                        record,
                        AgentEventType.RUN_FAILED,
                        {"code": "RUN_INPUT_MISSING", "message": "本轮输入暂时无法读取"},
                    )
                    return
                events = self._execute_resume_record(record, answers)
            else:
                message_id = record.metadata.get("input_message_id")
                input_message = self._message_store.get_for_conversation(
                    record.conversation_id, message_id
                ) if isinstance(message_id, str) else None
                if input_message is None:
                    record.status = RunStatus.FAILED
                    record.metadata["error_summary"] = "本轮输入暂时无法读取"
                    yield self._event(
                        record,
                        AgentEventType.RUN_FAILED,
                        {"code": "RUN_INPUT_MISSING", "message": "本轮输入暂时无法读取"},
                    )
                    return
                blocks = input_message.content.get("blocks", [])
                message_text = _message_text(blocks)
                graph_input = dict(record.metadata.get("graph_context") or {})
                graph_input.update({
                    "messages": [HumanMessage(content=message_text)],
                    "original_request": message_text,
                    "resume_answers": {},
                    "agent": self._agent,
                    "principal_id": record.principal_id,
                    "conversation_id": record.conversation_id,
                    "run_id": record.run_id,
                    "task_result_id": record.metadata.get("task_result_id"),
                    "attachment_ids": record.metadata.get("attachment_ids", []),
                })
                if self._agent == LISTING_AGENT:
                    graph_input["question_round_count"] = 0
                events = self._stream_graph(
                    record=record,
                    graph_input=graph_input,
                    title_source_message=(
                        message_text if record.metadata.get("is_new_conversation") else None
                    ),
                )

            async for event in events:
                yield event
        finally:
            if lock_acquired:
                # 终止事件由 Worker 消费者先写入 Redis，再请求下一事件；此处
                # 随生成器收尾保存终态并释放锁。
                if record is not None:
                    self._run_store.save(record)
                await self._run_lock.release(run_lock_key)

    def resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str = "local-development",
        request_id: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """兼容同步恢复；HTTP 恢复通过 prepare_resume 后派发后台任务。"""
        record = self.prepare_resume(
            conversation_id=conversation_id,
            run_id=run_id,
            answers=answers,
            principal_id=principal_id,
            request_id=request_id or self._id_generator.next_id_string(),
        )
        return self.execute_prepared(record.run_id)

    def prepare_resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str,
        request_id: str,
    ) -> RunRecord:
        """验证追问答案并把恢复请求持久化为可幂等派发的 queued 运行。"""
        record = self._run_store.get(run_id)
        request_hash = hashlib.sha256(json.dumps(
            answers, sort_keys=True, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        if (
            record is not None
            and record.conversation_id == conversation_id
            and record.principal_id == principal_id
            and record.agent == self._agent
            and record.metadata.get("resume_request_id") == request_id
        ):
            if record.metadata.get("resume_request_hash") != request_hash:
                raise AgentRunRequestConflictError()
            if record.status == RunStatus.QUEUED and not record.metadata.get("resume_message_id"):
                for _ in range(40):
                    time.sleep(0.025)
                    record = self._run_store.get(run_id) or record
                    if record.metadata.get("resume_message_id"):
                        break
                if not record.metadata.get("resume_message_id"):
                    self._save_resume_message(record, answers)
            return record
        if (
            record is None
            or record.status != RunStatus.WAITING
            or record.conversation_id != conversation_id
            or record.principal_id != principal_id
            or record.agent != self._agent
        ):
            raise RunNotResumableError()
        pending_question_ids = set(record.metadata.get("pending_question_ids", []))
        if not pending_question_ids or set(answers) != pending_question_ids:
            raise InvalidResumeAnswersError()
        pending_questions_data = record.metadata.get("pending_questions")
        question_titles: dict[str, str] = {}
        if isinstance(pending_questions_data, list):
            try:
                pending_questions = QuestionPayload(questions=pending_questions_data)
                pending_questions.validate_answers(answers)
                question_titles = {
                    question.id: question.title
                    for question in pending_questions.questions
                }
            except ValueError as error:
                raise InvalidResumeAnswersError() from error
        if "question_round_count" not in record.metadata:
            # 兼容升级前创建、只持久化了问题 ID 的等待中运行。
            record.metadata["question_round_count"] = 1
        record.metadata.update({
            "action": "resume",
            "resume_request_id": request_id,
            "resume_request_hash": request_hash,
            "resume_answers": answers,
        })
        record.status = RunStatus.QUEUED
        self._run_store.save(record)
        self._save_resume_message(record, answers)
        return record

    def _save_resume_message(self, record: RunRecord, answers: dict[str, Any]) -> None:
        """把追问回答按现有消息内容块存入会话历史。"""
        question_titles: dict[str, str] = {}
        questions_data = record.metadata.get("pending_questions")
        if isinstance(questions_data, list):
            with suppress(ValueError):
                questions = QuestionPayload(questions=questions_data)
                question_titles = {question.id: question.title for question in questions.questions}
        answer_text = "\n".join(
            f"{question_id}: {', '.join(value) if isinstance(value, list) else value}"
            for question_id, value in answers.items()
        )
        message_id = self._message_store.save(
            record.conversation_id,
            "user",
            {
                "blocks": [
                    {"type": "text", "text": answer_text},
                    {
                        "type": "question_answers",
                        "answers": answers,
                        **({"question_titles": question_titles} if question_titles else {}),
                    },
                ]
            },
        )
        record.metadata["resume_message_id"] = message_id
        self._run_store.save(record)

    def _execute_resume_record(
        self,
        record: RunRecord,
        answers: dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        """从已校验并保存的结构化答案恢复 LangGraph Checkpoint。"""
        graph_input = {
            "messages": [HumanMessage(content=json.dumps(answers, ensure_ascii=False))],
            "resume_answers": answers,
            "agent": self._agent,
            "principal_id": record.principal_id,
            "conversation_id": record.conversation_id,
            "run_id": record.run_id,
            "task_result_id": record.metadata.get("task_result_id"),
            "attachment_ids": record.metadata.get("attachment_ids", []),
        }
        if self._agent == LISTING_AGENT:
            question_round_count = record.metadata.get("question_round_count", 0)
            if (
                not isinstance(question_round_count, int)
                or isinstance(question_round_count, bool)
            ):
                question_round_count = 0
            graph_input["question_round_count"] = question_round_count
        return self._stream_graph(record=record, graph_input=graph_input)

    def cancel(self, *, run_id: str, principal_id: str) -> None:
        """校验运行归属后通过共享信号请求 Worker 停止。"""
        record = self._run_store.get(run_id)
        if (
            record is None
            or record.principal_id != principal_id
            or record.agent != self._agent
            or record.status not in {RunStatus.QUEUED, RunStatus.RUNNING}
        ):
            raise RunNotCancellableError()
        if self._cancel_signal is not None:
            self._cancel_signal.request_cancel(run_id)
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
        record.status = RunStatus.RUNNING
        self._run_store.save(record)
        title_task: asyncio.Task[str | None] | None = None
        cancel_monitor: asyncio.Task[None] | None = None
        try:
            await self._run_lock.acquire(scope_key)
            lock_acquired = True
            if self._cancel_signal is not None:
                cancel_monitor = asyncio.create_task(
                    self._watch_shared_cancel(record.run_id, cancel_event)
                )
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
                        if node_name in self._streaming_response_nodes and content:
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
                                        # 特殊智能体的回复可能要等任务或证据校验完成；仅拆分最终安全文本。
                                        for text_chunk in _text_chunks(missing_content):
                                            yield self._event(
                                                record,
                                                AgentEventType.MESSAGE_DELTA,
                                                {"content": text_chunk},
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
                        await self._run_lock.release(scope_key)
                finally:
                    self._cancel_events.pop(record.run_id, None)
                    if cancel_monitor is not None:
                        cancel_monitor.cancel()
                        with suppress(asyncio.CancelledError):
                            await cancel_monitor

    async def _watch_shared_cancel(
        self,
        run_id: str,
        cancel_event: asyncio.Event,
    ) -> None:
        """轮询 Redis 取消标志，使 API 实例的显式停止到达执行 Worker。"""
        while not cancel_event.is_set():
            try:
                requested = await asyncio.to_thread(
                    self._cancel_signal.is_cancel_requested,
                    run_id,
                )
            except Exception:
                logger.warning("读取共享取消信号失败 run_id=%s", run_id)
                await asyncio.sleep(1)
                continue
            if requested:
                cancel_event.set()
                return
            await asyncio.sleep(0.5)

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
                    "assistant",
                    text_content(message.content),
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
                tool_data = payload.get("data", {})
                questions = QuestionPayload.model_validate(
                    {"questions": tool_data.get("questions")}
                )
            except ValueError:
                yield self._event(
                    record,
                    AgentEventType.RUN_FAILED,
                    {"code": "INVALID_QUESTION_PAYLOAD", "message": "追问信息格式不正确"},
                )
                return
            question_round_count = record.metadata.get("question_round_count", 0)
            if (
                not isinstance(question_round_count, int)
                or isinstance(question_round_count, bool)
            ):
                question_round_count = 0
            if question_round_count >= MAX_QUESTION_ROUNDS_PER_RUN:
                record.status = RunStatus.FAILED
                yield self._event(
                    record,
                    AgentEventType.RUN_FAILED,
                    {
                        "code": "QUESTION_ROUND_LIMIT",
                        "message": (
                            f"本次处理最多补充 {MAX_QUESTION_ROUNDS_PER_RUN} 轮，"
                            "仍有必要信息缺失。请在聊天框中一次性补充剩余信息后重新提交；"
                            "系统不会根据缺失信息猜测并生成结果。"
                        ),
                    },
                )
                return
            question_round = question_round_count + 1
            record.metadata["question_round_count"] = question_round
            question_data = questions.model_dump(mode="json", exclude_none=True)
            question_data["question_round"] = question_round
            question_data["max_question_rounds"] = MAX_QUESTION_ROUNDS_PER_RUN
            record.metadata["pending_questions"] = question_data["questions"]
            record.metadata["pending_question_ids"] = [
                question.id for question in questions.questions
            ]
            question_message_id = self._message_store.save(
                record.conversation_id,
                "assistant",
                {
                    "blocks": [
                        {
                            "type": "text",
                            "text": "\n".join(
                                "\n".join(
                                    text
                                    for text in (question.title, question.prompt)
                                    if text
                                )
                                for question in questions.questions
                            ),
                        },
                        {
                            "type": "question_batch",
                            "run_id": record.run_id,
                            "question_round": question_round,
                            "max_question_rounds": MAX_QUESTION_ROUNDS_PER_RUN,
                            "questions": question_data["questions"],
                        },
                    ]
                },
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
                question_data,
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
        checkpoint_agent_name = CHECKPOINT_AGENT_NAMESPACE_COMPATIBILITY.get(
            record.agent,
            record.agent,
        )
        return f"{record.principal_id}:{checkpoint_agent_name}:{record.conversation_id}"


def build_memory_runner(
    settings: AppSettings,
    graph: Any | None = None,
    model_provider: ChatModelProvider | None = None,
    *,
    conversation_store: ConversationStore | None = None,
    message_store: MessageStore | None = None,
    agent: AgentType = COMMON_AGENT,
    task_result_store: TaskResultStore | None = None,
    attachment_store: AttachmentStore | None = None,
    title_generator: ConversationTitleGenerator | None = None,
) -> AgentRunner:
    """创建供测试显式使用的内存运行器，不参与应用默认启动流程。"""
    checkpointer = MemoryCheckpointProvider().get_checkpointer()
    return build_agent_runner(
        settings=settings,
        checkpointer=checkpointer,
        run_store=MemoryRunStore(),
        run_lock=MemoryRunLock(),
        conversation_store=conversation_store or MemoryConversationStore(),
        message_store=message_store or MemoryMessageStore(),
        event_sequence=MemoryEventSequence(),
        model_provider=model_provider,
        graph=graph,
        agent=agent,
        task_result_store=task_result_store or MemoryTaskResultStore(),
        attachment_store=attachment_store or MemoryAttachmentStore(),
        title_generator=title_generator,
        id_generator=get_snowflake_generator(settings.snowflake_worker_id),
    )


def build_agent_runner(
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
    agent: AgentType = COMMON_AGENT,
    task_result_store: TaskResultStore | None = None,
    attachment_store: AttachmentStore | None = None,
    title_generator: ConversationTitleGenerator | None = None,
    id_generator: SnowflakeIdGenerator | None = None,
    cancel_signal: Any | None = None,
) -> AgentRunner:
    """用注入的存储协议为一个 agent 组装运行器。"""
    provider = model_provider or OpenAICompatibleProvider(settings)
    if graph is None:
        graph = build_agent_graph(checkpointer, provider.create_chat_model())
    resolved_title_generator = title_generator or ModelConversationTitleGenerator(
        provider,
        settings.conversation_title_timeout_seconds,
    )
    return AgentRunner(
        graph=graph,
        agent=agent,
        task_result_store=task_result_store,
        attachment_store=attachment_store,
        title_generator=resolved_title_generator,
        id_generator=id_generator,
        cancel_signal=cancel_signal,
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
