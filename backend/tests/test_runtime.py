"""通用运行时的对话、追问恢复和事件协议测试。"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from typing import Annotated, TypedDict

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver
from pydantic import PrivateAttr

from agent.constants import BASE_CONVERSATION_AGENT
from agent.errors import InvalidResumeAnswersError
from agent.persistence.memory import MemoryConversationStore, MemoryMessageStore
from agent.runner import AgentRunner, build_memory_runner
from agent.schemas.run import RunRecord, RunStatus
from agent.streaming.events import (
    AgentEvent,
    AgentEventType,
    RunTerminalStatus,
    get_run_terminal_status,
)
from agent.title import ConversationTitleGenerator
from agents.base_agent import BaseAgent, BaseAgentConfig
from agents.base_agent import create_basic_conversation_agent
from infra.settings import AppSettings
from tests.fake_models import (
    ScriptedQuestionCallingProvider,
    ScriptedToolCallingProvider,
)


async def _collect_events(stream: object) -> list[AgentEvent]:
    """消费公共异步事件流，保持测试只依赖运行时公开接口。"""
    return [event async for event in stream]  # type: ignore[attr-defined]


def _create_runtime() -> AgentRunner:
    """创建不访问网络且直接持有唯一图的内存运行器。"""
    return build_memory_runner(
        AppSettings(_env_file=None),
        model_provider=ScriptedToolCallingProvider(),
    )


async def test_chat_uses_natural_language_for_general_clarification() -> None:
    """通用对话通过助手文本追问，不再创建结构化题卡。"""
    runtime = _create_runtime()

    events = await _collect_events(
        runtime.stream_chat(message="帮我整理一个开发目标")
    )

    event_types = [event.event_type for event in events]
    assert AgentEventType.START in event_types
    assert not any(
        event.event_type == AgentEventType.MESSAGE
        and any(
            block.get("type") == "question"
            for block in event.data.get("content", {}).get("blocks", [])
        )
        for event in events
    )
    terminal = next(event for event in events if event.event_type == AgentEventType.END)
    assert terminal.data["status"] == RunTerminalStatus.COMPLETED.value
    completed = next(
        event for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "snapshot"
    )
    assert completed.data["content"]["blocks"][0]["text"] == "你希望整理哪类开发目标？"


async def test_malformed_question_tool_result_fails_instead_of_waiting_forever() -> None:
    """畸形追问载荷必须产生失败事件，不能进入无法恢复的等待状态。"""
    runner = _create_runtime()
    record = RunRecord(
        run_id="run",
        conversation_id="conversation",
        principal_id="developer-a",
        status=RunStatus.RUNNING,
    )
    message = ToolMessage(
        content='{"success":true,"data":{"questions":[]}}',
        tool_call_id="tool-1",
        name="ask_listing_questions",
    )

    events = [
        event async for event in runner._events_for_message(
            record,
            message,
            {"message_id": None, "blocks": [], "text_block_id": None},
            {},
        )
    ]

    assert events[0].event_type == AgentEventType.END
    assert events[0].data["status"] == RunTerminalStatus.FAILED.value
    assert events[0].data["error"]["code"] == "INVALID_QUESTION_PAYLOAD"


async def test_question_round_limit_rejects_a_fourth_round() -> None:
    """单次运行已追问三轮时拒绝继续发布第四轮。"""
    runner = _create_runtime()
    record = RunRecord(
        run_id="run",
        conversation_id="conversation",
        principal_id="developer-a",
        status=RunStatus.RUNNING,
        metadata={"question_round_count": 3},
    )
    message = ToolMessage(
        content=(
            '{"success":true,"data":{"questions":[{"id":"goal",'
            '"title":"请选择目标类型。","type":"SingleChoice",'
            '"options":[{"label":"订单","description":"订单处理目标"},'
            '{"label":"库存","description":"库存处理目标"},'
            '{"label":"售后","description":"售后处理目标"},'
            '{"label":"其他","description":"其他业务目标"}],'
            '"allow_custom_input":false}]}}'
        ),
        tool_call_id="tool-1",
        name="ask_listing_questions",
    )

    events = [
        event async for event in runner._events_for_message(
            record,
            message,
            {"message_id": None, "blocks": [], "text_block_id": None},
            {},
        )
    ]

    assert len(events) == 1
    assert events[0].event_type == AgentEventType.END
    assert events[0].data["status"] == RunTerminalStatus.FAILED.value
    assert events[0].data["error"]["code"] == "QUESTION_ROUND_LIMIT"
    assert record.metadata["question_round_count"] == 3


async def test_basic_conversation_forwards_model_chunks_before_completion() -> None:
    """无工具基座图实时转发模型片段，并在完成事件中保留完整文本。"""
    chat_model = _StreamingReplyModel()
    assistant = BaseAgent(
        config=BaseAgentConfig(
            agent=BASE_CONVERSATION_AGENT,
            system_prompt="直接回答用户。",
        ),
        chat_model=chat_model,
        checkpointer=MemorySaver(),
    )
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=assistant.compiled_graph,
        agent=BASE_CONVERSATION_AGENT,
        title_generator=_UnavailableTitleGenerator(),
    )

    events = []
    stream_completed_at_delta: list[bool] = []
    async for event in runtime.stream_chat(message="请回答"):
        events.append(event)
        if (
            event.event_type == AgentEventType.MESSAGE
            and event.data.get("operation") == "delta"
        ):
            stream_completed_at_delta.append(chat_model.stream_completed)
            if len(stream_completed_at_delta) == 1:
                chat_model.continue_streaming()

    deltas = [
        event.data["text"]
        for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "delta"
    ]
    completed = next(
        event
        for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "snapshot"
    )
    final_text = completed.data["content"]["blocks"][0]["text"]
    assert deltas
    assert stream_completed_at_delta and not stream_completed_at_delta[0]
    assert "".join(deltas) == final_text == "你好，世界"
    delta_events = [
        event for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "delta"
    ]
    assert all(event.data["message_id"] == completed.data["message_id"] for event in delta_events)
    assert all(event.data["block_id"] == completed.data["content"]["blocks"][0]["id"] for event in delta_events)
    assert events.index(delta_events[-1]) < events.index(completed)
    expected_offset = 0
    for event in delta_events:
        assert event.data["offset"] == expected_offset
        expected_offset += len(event.data["text"])


async def test_basic_agent_question_card_waits_and_resumes_the_same_run() -> None:
    """基础助手题卡进入 WAITING，用户选择后同一 run 继续生成回答。"""

    message_store = MemoryMessageStore()
    assistant = create_basic_conversation_agent(
        agent=BASE_CONVERSATION_AGENT,
        chat_model=ScriptedQuestionCallingProvider().create_chat_model(),
        checkpointer=MemorySaver(),
    )
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=assistant.compiled_graph,
        message_store=message_store,
        agent=BASE_CONVERSATION_AGENT,
        title_generator=_UnavailableTitleGenerator(),
    )

    question_events = await _collect_events(
        runtime.stream_chat(
            message="请用题卡让我选一个计划风格。",
            principal_id="question-user",
        )
    )
    start_event = next(
        event for event in question_events if event.event_type == AgentEventType.START
    )
    waiting_event = next(
        event for event in question_events if event.event_type == AgentEventType.END
    )
    question_snapshot = next(
        event
        for event in question_events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "snapshot"
        and any(
            block.get("type") == "question"
            for block in event.data.get("content", {}).get("blocks", [])
        )
    )

    assert waiting_event.data["status"] == RunTerminalStatus.WAITING.value
    assert question_snapshot.run_id == start_event.run_id
    question_block = next(
        block
        for block in question_snapshot.data["content"]["blocks"]
        if block.get("type") == "question"
    )
    assert question_block["questions"][0]["type"] == "SingleChoice"

    for request_id, invalid_answers in (
        ("invalid-question-id", {"unknown_question": "稳步推进"}),
        ("invalid-option", {"plan_style": "未提供的选项"}),
    ):
        with pytest.raises(InvalidResumeAnswersError):
            runtime.prepare_resume(
                conversation_id=start_event.conversation_id,
                run_id=start_event.run_id,
                answers=invalid_answers,
                principal_id="question-user",
                request_id=request_id,
            )

    answer_events = await _collect_events(
        runtime.resume(
            conversation_id=start_event.conversation_id,
            run_id=start_event.run_id,
            answers={"plan_style": "稳步推进"},
            principal_id="question-user",
        )
    )
    completed_event = next(
        event for event in answer_events if event.event_type == AgentEventType.END
    )
    final_snapshot = next(
        event
        for event in answer_events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "snapshot"
        and any(
            block.get("type") == "text"
            for block in event.data.get("content", {}).get("blocks", [])
        )
    )

    assert completed_event.data["status"] == RunTerminalStatus.COMPLETED.value
    assert completed_event.run_id == start_event.run_id
    assert final_snapshot.run_id == start_event.run_id
    assert final_snapshot.data["content"]["blocks"][0]["text"] == (
        "我会按“稳步推进”的风格安排计划。"
    )
    history = message_store.list_by_conversation(
        start_event.conversation_id,
        limit=10,
        before_message_id=None,
    )
    assert any(
        block.get("type") == "question"
        for message in history
        for block in message.content.get("blocks", [])
    )
    assert any(
        message.role == "user"
        and any(
            block.get("type") == "text" and "稳步推进" in block.get("text", "")
            for block in message.content.get("blocks", [])
        )
        for message in history
    )


async def test_completed_messages_are_sent_as_multiple_deltas() -> None:
    """没有模型 token 流的任务型智能体也会分段发送已完成的安全文本。"""
    reply = "已完成安全结果。" * 8
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=_long_reply_graph_factory(MemorySaver(), reply),
        title_generator=_UnavailableTitleGenerator(),
    )

    events = await _collect_events(runtime.stream_chat(message="开始任务"))

    deltas = [
        event.data["text"]
        for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "delta"
    ]
    completed = next(
        event
        for event in events
        if event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "snapshot"
    )
    final_text = completed.data["content"]["blocks"][0]["text"]
    assert len(deltas) > 1
    assert "".join(deltas) == final_text == reply
    assert [event.data["offset"] for event in events if (
        event.event_type == AgentEventType.MESSAGE
        and event.data.get("operation") == "delta"
    )] == [
        sum(len(text) for text in deltas[:index])
        for index in range(len(deltas))
    ]


class _SlowState(TypedDict):
    """超时测试使用的最小图状态。"""

    messages: Annotated[list[BaseMessage], add_messages]


async def _slow_node(state: _SlowState) -> dict[str, list[AIMessage]]:
    """模拟超过运行预算的节点，不访问任何外部服务。"""
    del state
    await asyncio.sleep(1.1)
    return {"messages": [AIMessage(content="不应到达")]}


def _slow_graph_factory(checkpointer: object) -> object:
    """创建用于验证全局运行超时的测试图。"""
    graph = StateGraph(_SlowState)
    graph.add_node("slow", _slow_node)
    graph.add_edge(START, "slow")
    return graph.compile(checkpointer=checkpointer)


async def test_runtime_stops_graph_after_configured_timeout() -> None:
    """图超过运行预算后返回稳定超时错误，不泄露 asyncio 异常。"""
    runtime = build_memory_runner(
        AppSettings(agent_run_timeout_seconds=1, _env_file=None),
        graph=_slow_graph_factory(MemorySaver()),
    )

    events = await _collect_events(
        runtime.stream_chat(message="开始")
    )

    failed = next(
        event
        for event in events
        if get_run_terminal_status(event) == RunTerminalStatus.FAILED
    )
    assert failed.data == {
        "status": RunTerminalStatus.FAILED.value,
        "error": {
            "code": "AGENT_RUN_TIMEOUT",
            "message": "智能体运行超时，请稍后重试",
        },
    }


async def test_cancel_interrupts_long_running_node_without_waiting_for_update() -> None:
    """取消信号会立即打断长节点，并向原事件流发送取消终止事件。"""
    runtime = build_memory_runner(
        AppSettings(agent_run_timeout_seconds=10, _env_file=None),
        graph=_slow_graph_factory(MemorySaver()),
    )
    stream = runtime.stream_chat(
        message="开始",
        principal_id="developer-a",
    )
    started = await anext(stream)
    loop = asyncio.get_running_loop()
    cancel_started_at = loop.time()

    runtime.cancel(
        run_id=started.run_id,
        principal_id="developer-a",
    )
    remaining_events = [event async for event in stream]

    assert loop.time() - cancel_started_at < 0.5
    assert [event.event_type for event in remaining_events] == [
        AgentEventType.END
    ]
    assert remaining_events[0].data["status"] == RunTerminalStatus.CANCELLED.value


async def test_second_run_on_same_conversation_fails_without_orphan_record() -> None:
    """同会话并发请求快速返回安全事件，且不会影响首个运行取消清理。"""
    runtime = build_memory_runner(
        AppSettings(agent_run_timeout_seconds=10, _env_file=None),
        graph=_slow_graph_factory(MemorySaver()),
    )
    first_stream = runtime.stream_chat(
        message="第一次",
        conversation_id="shared-conversation",
        principal_id="developer-a",
    )
    first_started = await anext(first_stream)

    second_events = await _collect_events(
        runtime.stream_chat(
            message="第二次",
            conversation_id="shared-conversation",
            principal_id="developer-a",
        )
    )

    assert second_events[-1].event_type == AgentEventType.END
    assert second_events[-1].data["status"] == RunTerminalStatus.FAILED.value
    assert second_events[-1].data["error"]["code"] == "RUN_BUSY"
    runtime.cancel(
        run_id=first_started.run_id,
        principal_id="developer-a",
    )
    await _collect_events(first_stream)


async def test_conversation_id_is_scoped_to_principal_and_agent() -> None:
    """客户端即使知道会话标识，也不能跨主体继续同一 Checkpoint。"""
    runtime = _create_runtime()
    await _collect_events(
        runtime.stream_chat(
            message="创建会话",
            conversation_id="owned-conversation",
            principal_id="developer-a",
        )
    )
    from agent.errors import ConversationAccessDeniedError

    with pytest.raises(ConversationAccessDeniedError):
        runtime.stream_chat(
            message="尝试访问",
            conversation_id="owned-conversation",
            principal_id="developer-b",
        )


class _FixedTitleGenerator:
    """记录首轮标题请求并返回固定模型结果。"""

    def __init__(self) -> None:
        self.messages: list[str] = []

    async def generate_title(self, first_user_message: str) -> str | None:
        self.messages.append(first_user_message)
        return "模型理解后的标题"


async def _reply_node(state: _SlowState) -> dict[str, list[AIMessage]]:
    """为标题运行时测试提供不访问网络的快速回复节点。"""
    del state
    return {"messages": [AIMessage(content="收到")]}


def _reply_graph_factory(checkpointer: object) -> object:
    """创建用于验证标题生成时机的简短对话图。"""
    graph = StateGraph(_SlowState)
    graph.add_node("reply", _reply_node)
    graph.add_edge(START, "reply")
    return graph.compile(checkpointer=checkpointer)


def _long_reply_node(
    state: _SlowState,
    *,
    reply: str,
) -> dict[str, list[AIMessage]]:
    """构造任务完成后返回固定安全文本的测试节点。"""
    del state
    return {"messages": [AIMessage(content=reply)]}


def _long_reply_graph_factory(checkpointer: object, reply: str) -> object:
    """创建用于验证最终文本分段发送的图。"""
    graph = StateGraph(_SlowState)
    graph.add_node("reply", lambda state: _long_reply_node(state, reply=reply))
    graph.add_edge(START, "reply")
    return graph.compile(checkpointer=checkpointer)


class _StreamingReplyModel(BaseChatModel):
    """模拟支持 astream 的对话模型，避免流式运行时测试访问网络。"""

    _stream_completed: bool = PrivateAttr(default=False)
    _continue_streaming: asyncio.Event = PrivateAttr(default_factory=asyncio.Event)

    @property
    def stream_completed(self) -> bool:
        return self._stream_completed

    @property
    def _llm_type(self) -> str:
        return "streaming-test"

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ) -> ChatResult:
        """提供与流式输出一致的完整回答，满足聊天模型同步接口。"""
        del messages, stop, run_manager, kwargs
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content="你好，世界"))]
        )

    def _stream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ) -> Iterator[ChatGenerationChunk]:
        """分两段产生面向用户的回答文本。"""
        del messages, stop, run_manager, kwargs
        yield ChatGenerationChunk(message=AIMessageChunk(content="你好"))
        yield ChatGenerationChunk(message=AIMessageChunk(content="，世界"))
        self._stream_completed = True

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: object = None,
        **kwargs: object,
    ) -> AsyncIterator[ChatGenerationChunk]:
        """等待测试收到首个增量事件后再发送剩余内容，固定流式时序。"""
        del messages, stop, run_manager, kwargs
        yield ChatGenerationChunk(message=AIMessageChunk(content="你好"))
        await asyncio.wait_for(self._continue_streaming.wait(), timeout=5)
        yield ChatGenerationChunk(message=AIMessageChunk(content="，世界"))
        self._stream_completed = True

    def continue_streaming(self) -> None:
        """允许模型发送第二段，避免测试依赖线程调度速度。"""
        self._continue_streaming.set()


async def test_title_is_generated_only_for_first_message_of_new_conversation() -> None:
    """同一会话仅首轮调用模型命名，后续消息不会覆盖生成标题。"""
    title_generator: ConversationTitleGenerator = _FixedTitleGenerator()
    conversation_store = MemoryConversationStore()
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=_reply_graph_factory(MemorySaver()),
        conversation_store=conversation_store,
        title_generator=title_generator,
    )

    first_events = await _collect_events(
        runtime.stream_chat(message="首条用户消息描述了一个查询助手")
    )
    conversation_id = first_events[0].conversation_id
    await _collect_events(
        runtime.stream_chat(
            message="第二轮补充信息",
            conversation_id=conversation_id,
        )
    )

    conversations = conversation_store.list_by_owner("local-development", 10, 0)
    assert title_generator.messages == ["首条用户消息描述了一个查询助手"]
    assert conversations[0].title == "模型理解后的标题"


class _UnavailableTitleGenerator:
    """模拟标题模型没有返回可用结果。"""

    async def generate_title(self, first_user_message: str) -> str | None:
        del first_user_message
        return None


async def test_title_falls_back_to_first_message_when_model_returns_no_title() -> None:
    """标题模型未返回内容时仍保存规范化后的首条消息摘要。"""
    conversation_store = MemoryConversationStore()
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=_reply_graph_factory(MemorySaver()),
        conversation_store=conversation_store,
        title_generator=_UnavailableTitleGenerator(),
    )

    await _collect_events(runtime.stream_chat(message="  生成   回退标题  "))

    conversations = conversation_store.list_by_owner("local-development", 10, 0)
    assert conversations[0].title == "生成 回退标题"
