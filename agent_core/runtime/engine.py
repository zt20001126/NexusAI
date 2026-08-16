"""传输层无关的通用智能体运行引擎。"""

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langgraph.errors import GraphRecursionError

from agent_core.contracts.agent import AgentDefinition
from agent_core.contracts.events import AgentEvent, AgentEventType
from agent_core.contracts.infrastructure import (
    ConversationStore,
    EventBus,
    EventSequence,
    RunLock,
    RunStore,
    TaskDispatcher,
)
from agent_core.contracts.runtime import RunRecord, RunStatus
from agent_core.contracts.tools import ToolResult
from agent_core.errors import (
    InvalidResumeAnswersError,
    AgentDefinitionError,
    ConversationAccessDeniedError,
    RunNotCancellableError,
    RunBusyError,
    RunNotResumableError,
)
from agent_core.registry import AgentRegistry

logger = logging.getLogger(__name__)


class AgentRuntime:
    """编排智能体图、会话锁、恢复记录和统一事件。"""

    def __init__(
        self,
        *,
        registry: AgentRegistry,
        checkpointer: Any,
        run_store: RunStore,
        run_lock: RunLock,
        conversation_store: ConversationStore,
        event_bus: EventBus,
        task_dispatcher: TaskDispatcher,
        event_sequence: EventSequence,
        max_steps: int,
        max_tool_calls: int,
        max_output_chars: int,
        run_timeout_seconds: int,
    ) -> None:
        """注入基础设施接口；默认工厂提供不访问网络的内存实现。"""
        self._registry = registry
        self._checkpointer = checkpointer
        self._run_store = run_store
        self._run_lock = run_lock
        self._conversation_store = conversation_store
        self._event_bus = event_bus
        self._task_dispatcher = task_dispatcher
        self._event_sequence = event_sequence
        self._max_steps = max_steps
        self._max_tool_calls = max_tool_calls
        self._max_output_chars = max_output_chars
        self._run_timeout_seconds = run_timeout_seconds
        self._graphs: dict[str, Any] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    def register(self, definition: AgentDefinition) -> None:
        """注册并编译业务智能体图，编译阶段不会连接外部基础设施。"""
        graph = definition.graph_factory(self._checkpointer)
        graph_pause_tools = getattr(graph, "pause_tool_names", frozenset())
        if graph_pause_tools != definition.pause_tool_names:
            raise AgentDefinitionError()
        self._registry.register(definition)
        self._graphs[definition.agent_id] = graph

    def list_agents(self) -> list[AgentDefinition]:
        """返回可供 API 展示的智能体定义。"""
        return self._registry.list_definitions()

    def stream_chat(
        self,
        *,
        agent_id: str,
        message: str,
        conversation_id: str | None = None,
        principal_id: str = "local-development",
    ) -> AsyncIterator[AgentEvent]:
        """启动新运行并返回统一异步事件流。"""
        self._registry.get(agent_id)
        resolved_conversation_id = conversation_id or uuid.uuid4().hex
        conversation = self._conversation_store.get(resolved_conversation_id)
        if conversation is not None and (
            conversation.get("agent_id") != agent_id
            or conversation.get("principal_id") != principal_id
        ):
            raise ConversationAccessDeniedError()
        self._conversation_store.save(
            resolved_conversation_id,
            {"agent_id": agent_id, "principal_id": principal_id},
        )
        run_id = uuid.uuid4().hex
        record = RunRecord(
            run_id=run_id,
            conversation_id=resolved_conversation_id,
            agent_id=agent_id,
            principal_id=principal_id,
            status=RunStatus.RUNNING,
        )
        self._run_store.save(record)
        graph_input = {
            "messages": [HumanMessage(content=message)],
            "original_request": message,
            "resume_answers": {},
        }
        return self._stream_graph(record=record, graph_input=graph_input)

    def resume(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str = "local-development",
    ) -> AsyncIterator[AgentEvent]:
        """校验等待状态后，使用受控答案从相同会话恢复图。"""
        self._registry.get(agent_id)
        record = self._run_store.get(run_id)
        if (
            record is None
            or record.status != RunStatus.WAITING
            or record.agent_id != agent_id
            or record.conversation_id != conversation_id
            or record.principal_id != principal_id
        ):
            raise RunNotResumableError()
        pending_question_ids = set(record.metadata.get("pending_question_ids", []))
        if not pending_question_ids or set(answers) != pending_question_ids:
            raise InvalidResumeAnswersError()
        record.status = RunStatus.RUNNING
        self._run_store.save(record)
        graph_input = {
            "messages": [HumanMessage(content=json.dumps(answers, ensure_ascii=False))],
            "resume_answers": answers,
        }
        return self._stream_graph(record=record, graph_input=graph_input)

    def cancel(self, *, agent_id: str, run_id: str, principal_id: str) -> None:
        """校验运行归属和状态后设置进程内取消标记。"""
        record = self._run_store.get(run_id)
        if (
            record is None
            or record.agent_id != agent_id
            or record.principal_id != principal_id
            or record.status != RunStatus.RUNNING
        ):
            raise RunNotCancellableError()
        cancel_event = self._cancel_events.setdefault(run_id, asyncio.Event())
        cancel_event.set()

    def heartbeat(self, reference: AgentEvent) -> AgentEvent:
        """基于最近事件生成同一运行的协议级心跳。"""
        sequence = self._event_sequence.next(reference.conversation_id)
        return AgentEvent(
            event_id=f"{reference.conversation_id}:{sequence}",
            event_type=AgentEventType.HEARTBEAT,
            conversation_id=reference.conversation_id,
            run_id=reference.run_id,
            sequence=sequence,
            data={},
        )

    def prepare_delivery(self, event: AgentEvent) -> AgentEvent:
        """在实际发送层重新分配游标，确保心跳和业务事件严格单调。"""
        sequence = self._event_sequence.next(event.conversation_id)
        return event.model_copy(
            update={
                "event_id": f"{event.conversation_id}:{sequence}",
                "sequence": sequence,
            }
        )

    async def publish_event(self, event: AgentEvent) -> None:
        """按适配协议发布实际即将发送的事件，支持后续游标重放。"""
        await self._event_bus.publish(event)

    def subscribe_events(
        self,
        conversation_id: str,
        after: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """订阅会话事件历史及后续实时事件。"""
        return self._event_bus.subscribe(conversation_id, after)

    def submit_task(self, task_name: str, payload: dict[str, Any]) -> str:
        """通过已配置任务适配器提交长耗时工作。"""
        return self._task_dispatcher.submit(task_name, payload)

    async def _stream_graph(
        self,
        *,
        record: RunRecord,
        graph_input: dict[str, Any],
    ) -> AsyncIterator[AgentEvent]:
        """执行已编译图并将节点更新映射为稳定事件。"""
        scope_key = self._scope_key(record)
        lock_acquired = False
        waiting_for_answer = False
        tool_call_count = 0
        output_char_count = 0
        cancel_event = self._cancel_events.setdefault(record.run_id, asyncio.Event())
        try:
            await self._run_lock.acquire(scope_key)
            lock_acquired = True
            self._registry.get(record.agent_id)
            graph = self._graphs[record.agent_id]
            yield self._event(record, AgentEventType.RUN_STARTED)
            config = {
                "configurable": {"thread_id": scope_key},
                "recursion_limit": self._max_steps,
            }
            async with asyncio.timeout(self._run_timeout_seconds):
                graph_stream = graph.astream(
                    graph_input,
                    config=config,
                    stream_mode=["messages", "updates"],
                )
                async for stream_item in self._cancel_aware_stream(
                    graph_stream,
                    cancel_event,
                ):
                    if stream_item is None:
                        record.status = RunStatus.CANCELLED
                        yield self._event(record, AgentEventType.RUN_CANCELLED)
                        return
                    stream_mode, payload = stream_item
                    if stream_mode == "messages":
                        message, metadata = payload
                        if (
                            isinstance(message, (AIMessage, AIMessageChunk))
                            and metadata.get("langgraph_node") == "agent"
                            and isinstance(message.content, str)
                            and message.content
                        ):
                            output_char_count += len(message.content)
                            if output_char_count > self._max_output_chars:
                                record.status = RunStatus.FAILED
                                yield self._event(
                                    record,
                                    AgentEventType.RUN_FAILED,
                                    {
                                        "code": "AGENT_OUTPUT_LIMIT",
                                        "message": "智能体输出超过允许长度",
                                    },
                                )
                                return
                            yield self._event(
                                record,
                                AgentEventType.MESSAGE_DELTA,
                                {"content": message.content},
                            )
                        continue
                    update = payload
                    for node_update in update.values():
                        if not isinstance(node_update, dict):
                            continue
                        for message in node_update.get("messages", []):
                            async for event in self._events_for_message(record, message):
                                if event.event_type == AgentEventType.TOOL_STARTED:
                                    tool_call_count += 1
                                    if tool_call_count > self._max_tool_calls:
                                        record.status = RunStatus.FAILED
                                        yield self._event(
                                            record,
                                            AgentEventType.RUN_FAILED,
                                            {
                                                "code": "AGENT_TOOL_CALL_LIMIT",
                                                "message": "工具调用次数超过允许范围",
                                            },
                                        )
                                        return
                                if event.event_type == AgentEventType.QUESTION_REQUIRED:
                                    waiting_for_answer = True
                                    record.metadata["pending_question_ids"] = [
                                        question.get("id")
                                        for question in event.data.get("questions", [])
                                        if isinstance(question, dict)
                                        and isinstance(question.get("id"), str)
                                    ]
                                yield event
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
                "智能体运行超时 agent_id=%s conversation_id=%s run_id=%s",
                record.agent_id,
                record.conversation_id,
                record.run_id,
            )
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "AGENT_RUN_TIMEOUT", "message": "智能体运行超时，请稍后重试"},
            )
        except asyncio.CancelledError:
            # SSE 客户端断开会取消事件生成器；保存取消状态后继续抛出，
            # 让 ASGI 服务器及时结束响应且不伪造一个客户端已收不到的终止事件。
            record.status = RunStatus.CANCELLED
            raise
        except Exception:
            record.status = RunStatus.FAILED
            logger.exception(
                "智能体运行失败 agent_id=%s conversation_id=%s run_id=%s",
                record.agent_id,
                record.conversation_id,
                record.run_id,
            )
            yield self._event(
                record,
                AgentEventType.RUN_FAILED,
                {"code": "AGENT_RUN_FAILED", "message": "智能体运行失败，请稍后重试"},
            )
        finally:
            self._run_store.save(record)
            if lock_acquired:
                self._run_lock.release(scope_key)
            self._cancel_events.pop(record.run_id, None)

    @staticmethod
    async def _cancel_aware_stream(
        stream: AsyncIterator[tuple[str, Any]],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[tuple[str, Any] | None]:
        """在等待图更新时同时监听取消信号，避免长节点阻塞取消。"""
        try:
            while True:
                next_item = asyncio.create_task(anext(stream))
                cancelled = asyncio.create_task(cancel_event.wait())
                done, _ = await asyncio.wait(
                    {next_item, cancelled},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if cancelled in done:
                    next_item.cancel()
                    with suppress(asyncio.CancelledError, StopAsyncIteration):
                        await next_item
                    yield None
                    return
                cancelled.cancel()
                with suppress(asyncio.CancelledError):
                    await cancelled
                try:
                    yield next_item.result()
                except StopAsyncIteration:
                    return
        finally:
            with suppress(Exception):
                await stream.aclose()

    async def _events_for_message(
        self,
        record: RunRecord,
        message: Any,
    ) -> AsyncIterator[AgentEvent]:
        """将 LangChain 消息转换为受控工具、追问或文本事件。"""
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls:
                yield self._event(
                    record,
                    AgentEventType.TOOL_STARTED,
                    {"tool_name": tool_call.get("name", "")},
                )
            if isinstance(message.content, str) and message.content:
                yield self._event(
                    record,
                    AgentEventType.MESSAGE_COMPLETED,
                    {"content": message.content},
                )
            return
        if not isinstance(message, ToolMessage):
            return
        payload = self._safe_tool_payload(message.content)
        definition = self._registry.get(record.agent_id)
        if message.name in definition.pause_tool_names:
            yield self._event(
                record,
                AgentEventType.QUESTION_REQUIRED,
                {"questions": payload.get("data", {}).get("questions", [])},
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

    @staticmethod
    def _safe_tool_payload(content: Any) -> dict[str, Any]:
        """使用统一 DTO 校验有界工具结果，畸形结果降级为稳定失败结构。"""
        raw_content = str(content)
        if len(raw_content) > 64_000:
            return {"success": False, "data": {}, "code": "INVALID_TOOL_RESULT"}
        try:
            result = ToolResult.model_validate_json(raw_content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return {"success": False, "data": {}, "code": "INVALID_TOOL_RESULT"}
        return result.model_dump()

    def _event(
        self,
        record: RunRecord,
        event_type: AgentEventType,
        data: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """生成带会话内有序游标的事件。"""
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
        """用可信主体和智能体隔离锁与 Checkpoint 内部键。"""
        return f"{record.principal_id}:{record.agent_id}:{record.conversation_id}"
