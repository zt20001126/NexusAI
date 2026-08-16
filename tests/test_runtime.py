"""通用运行时的对话、追问恢复和事件协议测试。"""

import asyncio
from typing import Annotated, TypedDict

import pytest
from langchain_core.messages import AIMessage, BaseMessage
from langgraph.constants import START
from langgraph.graph import StateGraph
from langgraph.graph.message import add_messages

from agent_core.contracts.agent import AgentDefinition
from agent_core.contracts.events import AgentEvent, AgentEventType
from agent_core.errors import InvalidResumeAnswersError
from agent_core.runtime.engine import AgentRuntime
from agent_core.runtime.factory import build_memory_runtime
from agents.example_agent.definition import create_example_agent_definition
from infra.settings import AppSettings


async def _collect_events(stream: object) -> list[AgentEvent]:
    """消费公共异步事件流，保持测试只依赖运行时公开接口。"""
    return [event async for event in stream]  # type: ignore[attr-defined]


def _create_runtime() -> AgentRuntime:
    """创建不访问网络的内存运行时并注册示例智能体。"""
    runtime = build_memory_runtime(AppSettings(_env_file=None))
    runtime.register(create_example_agent_definition())
    return runtime


async def test_chat_pauses_with_structured_question() -> None:
    """信息不足时，运行产生可恢复问题而不会错误发送完成事件。"""
    runtime = _create_runtime()

    events = await _collect_events(
        runtime.stream_chat(agent_id="example", message="帮我整理一个开发目标")
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


async def test_resume_executes_tool_and_completes_once() -> None:
    """提交问题答案后，从相同运行恢复，执行工具并且只完成一次。"""
    runtime = _create_runtime()
    paused_events = await _collect_events(
        runtime.stream_chat(agent_id="example", message="帮我整理一个开发目标")
    )
    paused = next(
        event
        for event in paused_events
        if event.event_type == AgentEventType.QUESTION_REQUIRED
    )

    resumed_events = await _collect_events(
        runtime.resume(
            agent_id="example",
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
    runtime = build_memory_runtime(
        AppSettings(agent_run_timeout_seconds=1, _env_file=None)
    )
    runtime.register(
        AgentDefinition(
            agent_id="slow",
            name="慢智能体",
            description="测试运行超时",
            graph_factory=_slow_graph_factory,
        )
    )

    events = await _collect_events(
        runtime.stream_chat(agent_id="slow", message="开始")
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
            agent_id="example",
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
            agent_id="example",
            conversation_id=paused.conversation_id,
            run_id=paused.run_id,
            answers={"unexpected": "value"},
            principal_id="developer-a",
        )


async def test_cancel_interrupts_long_running_node_without_waiting_for_update() -> None:
    """取消信号会立即打断长节点，并向原事件流发送取消终止事件。"""
    runtime = build_memory_runtime(
        AppSettings(agent_run_timeout_seconds=10, _env_file=None)
    )
    runtime.register(
        AgentDefinition(
            agent_id="slow",
            name="慢智能体",
            description="测试主动取消",
            graph_factory=_slow_graph_factory,
        )
    )
    stream = runtime.stream_chat(
        agent_id="slow",
        message="开始",
        principal_id="developer-a",
    )
    started = await anext(stream)
    loop = asyncio.get_running_loop()
    cancel_started_at = loop.time()

    runtime.cancel(
        agent_id="slow",
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
    runtime = build_memory_runtime(
        AppSettings(agent_run_timeout_seconds=10, _env_file=None)
    )
    runtime.register(
        AgentDefinition(
            agent_id="slow",
            name="慢智能体",
            description="测试会话互斥",
            graph_factory=_slow_graph_factory,
        )
    )
    first_stream = runtime.stream_chat(
        agent_id="slow",
        message="第一次",
        conversation_id="shared-conversation",
        principal_id="developer-a",
    )
    first_started = await anext(first_stream)

    second_events = await _collect_events(
        runtime.stream_chat(
            agent_id="slow",
            message="第二次",
            conversation_id="shared-conversation",
            principal_id="developer-a",
        )
    )

    assert second_events[-1].event_type == AgentEventType.RUN_FAILED
    assert second_events[-1].data["code"] == "RUN_BUSY"
    runtime.cancel(
        agent_id="slow",
        run_id=first_started.run_id,
        principal_id="developer-a",
    )
    await _collect_events(first_stream)


async def test_conversation_id_is_scoped_to_principal_and_agent() -> None:
    """客户端即使知道会话标识，也不能跨主体继续同一 Checkpoint。"""
    runtime = _create_runtime()
    await _collect_events(
        runtime.stream_chat(
            agent_id="example",
            message="创建会话",
            conversation_id="owned-conversation",
            principal_id="developer-a",
        )
    )
    from agent_core.errors import ConversationAccessDeniedError

    with pytest.raises(ConversationAccessDeniedError):
        runtime.stream_chat(
            agent_id="example",
            message="尝试访问",
            conversation_id="owned-conversation",
            principal_id="developer-b",
        )
