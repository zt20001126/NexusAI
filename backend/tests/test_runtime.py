"""通用运行时的对话、追问恢复和事件协议测试。"""

import asyncio
from collections.abc import Iterator
from typing import Annotated, TypedDict

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, BaseMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from agent.constants import BASE_CONVERSATION_AGENT_ID
from agent.errors import InvalidResumeAnswersError
from agent.persistence.memory import MemoryConversationStore
from agent.runner import AgentRunner, build_memory_runner
from agent.schemas.run import RunRecord, RunStatus
from agent.streaming.events import AgentEvent, AgentEventType
from agent.title import ConversationTitleGenerator
from agents.base_agent import create_basic_conversation_agent
from infra.settings import AppSettings
from tests.fake_models import ScriptedToolCallingProvider


async def _collect_events(stream: object) -> list[AgentEvent]:
    """消费公共异步事件流，保持测试只依赖运行时公开接口。"""
    return [event async for event in stream]  # type: ignore[attr-defined]


def _create_runtime() -> AgentRunner:
    """创建不访问网络且直接持有唯一图的内存运行器。"""
    return build_memory_runner(
        AppSettings(_env_file=None),
        model_provider=ScriptedToolCallingProvider(),
    )


async def test_chat_pauses_with_structured_question() -> None:
    """信息不足时，运行产生可恢复问题而不会错误发送完成事件。"""
    runtime = _create_runtime()

    events = await _collect_events(
        runtime.stream_chat(message="帮我整理一个开发目标")
    )

    event_types = [event.event_type for event in events]
    question = next(
        event
        for event in events
        if event.event_type == AgentEventType.QUESTION_REQUIRED
    )
    assert AgentEventType.RUN_STARTED in event_types
    assert AgentEventType.RUN_COMPLETED not in event_types
    assert question.data["questions"][0]["id"] == "goal"
    assert question.run_id
    assert question.conversation_id


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
        name="ask_user_question",
    )

    events = [event async for event in runner._events_for_message(record, message)]

    assert events[0].event_type == AgentEventType.RUN_FAILED
    assert events[0].data["code"] == "INVALID_QUESTION_PAYLOAD"


async def test_resume_executes_tool_and_completes_once() -> None:
    """提交问题答案后，从相同运行恢复，执行工具并且只完成一次。"""
    runtime = _create_runtime()
    paused_events = await _collect_events(
        runtime.stream_chat(message="帮我整理一个开发目标")
    )
    paused = next(
        event
        for event in paused_events
        if event.event_type == AgentEventType.QUESTION_REQUIRED
    )

    resumed_events = await _collect_events(
        runtime.resume(
            conversation_id=paused.conversation_id,
            run_id=paused.run_id,
            answers={"goal": "实现一个可复用的订单查询智能体"},
        )
    )

    event_types = [event.event_type for event in resumed_events]
    assert AgentEventType.MESSAGE_DELTA in event_types
    assert AgentEventType.TOOL_COMPLETED in event_types
    assert AgentEventType.MESSAGE_COMPLETED in event_types
    assert event_types.count(AgentEventType.RUN_COMPLETED) == 1
    final_message = next(
        event
        for event in resumed_events
        if event.event_type == AgentEventType.MESSAGE_COMPLETED
    )
    assert "订单查询智能体" in final_message.data["content"]


async def test_basic_conversation_forwards_model_chunks_before_completion() -> None:
    """基础对话助手实时转发模型片段，并在完成事件中保留完整文本。"""
    assistant = create_basic_conversation_agent(
        agent_id=BASE_CONVERSATION_AGENT_ID,
        chat_model=_StreamingReplyModel(),
        checkpointer=MemorySaver(),
    )
    runtime = build_memory_runner(
        AppSettings(_env_file=None),
        graph=assistant.compiled_graph,
        agent_id=BASE_CONVERSATION_AGENT_ID,
        title_generator=_UnavailableTitleGenerator(),
    )

    events = await _collect_events(runtime.stream_chat(message="请回答"))

    deltas = [
        event.data["content"]
        for event in events
        if event.event_type == AgentEventType.MESSAGE_DELTA
    ]
    completed = next(
        event
        for event in events
        if event.event_type == AgentEventType.MESSAGE_COMPLETED
    )
    assert deltas == ["你好", "，世界"]
    assert "".join(deltas) == completed.data["content"] == "你好，世界"
    first_delta_index = next(
        index
        for index, event in enumerate(events)
        if event.event_type == AgentEventType.MESSAGE_DELTA
    )
    assert first_delta_index < events.index(completed)


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
        event.data["content"]
        for event in events
        if event.event_type == AgentEventType.MESSAGE_DELTA
    ]
    completed = next(
        event
        for event in events
        if event.event_type == AgentEventType.MESSAGE_COMPLETED
    )
    assert len(deltas) > 1
    assert "".join(deltas) == completed.data["content"] == reply


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
        event for event in events if event.event_type == AgentEventType.RUN_FAILED
    )
    assert failed.data == {
        "code": "AGENT_RUN_TIMEOUT",
        "message": "智能体运行超时，请稍后重试",
    }


async def test_resume_rejects_answers_for_unknown_question() -> None:
    """恢复答案必须对应当前等待问题，不能向图状态注入任意字段。"""
    runtime = _create_runtime()
    paused_events = await _collect_events(
        runtime.stream_chat(
            message="帮我整理一个开发目标",
            principal_id="developer-a",
        )
    )
    paused = next(
        event
        for event in paused_events
        if event.event_type == AgentEventType.QUESTION_REQUIRED
    )

    with pytest.raises(InvalidResumeAnswersError):
        runtime.resume(
            conversation_id=paused.conversation_id,
            run_id=paused.run_id,
            answers={"unexpected": "value"},
            principal_id="developer-a",
        )


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
        AgentEventType.RUN_CANCELLED
    ]


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

    assert second_events[-1].event_type == AgentEventType.RUN_FAILED
    assert second_events[-1].data["code"] == "RUN_BUSY"
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
