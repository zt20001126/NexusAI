"""连接 HTTP DTO 与传输层无关运行时的应用编排服务。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Any

from agent_core.contracts.agent import AgentDefinition
from agent_core.contracts.events import AgentEvent
from agent_core.runtime.engine import AgentRuntime


class AgentApplicationService:
    """负责对话、恢复、取消和 SSE 心跳编排。"""

    def __init__(self, runtime: AgentRuntime, heartbeat_seconds: float) -> None:
        """注入唯一运行时和心跳周期。"""
        self._runtime = runtime
        self._heartbeat_seconds = heartbeat_seconds

    def list_agents(self) -> list[AgentDefinition]:
        """返回已注册智能体。"""
        return self._runtime.list_agents()

    async def chat(
        self,
        *,
        agent_id: str,
        message: str,
        conversation_id: str | None,
        principal_id: str,
    ) -> list[AgentEvent]:
        """执行非流式对话并收集完整事件。"""
        events: list[AgentEvent] = []
        async for event in self._runtime.stream_chat(
            agent_id=agent_id,
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
        ):
            delivered_event = self._runtime.prepare_delivery(event)
            await self._runtime.publish_event(delivered_event)
            events.append(delivered_event)
        return events

    def stream_chat(
        self,
        *,
        agent_id: str,
        message: str,
        conversation_id: str | None,
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """执行流式对话，并在图长时间无输出时插入协议级心跳。"""
        events = self._runtime.stream_chat(
            agent_id=agent_id,
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
        )
        return self.with_heartbeat(events)

    def resume(
        self,
        *,
        agent_id: str,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """校验主体后恢复运行，并继续提供协议级心跳。"""
        events = self._runtime.resume(
            agent_id=agent_id,
            conversation_id=conversation_id,
            run_id=run_id,
            answers=answers,
            principal_id=principal_id,
        )
        return self.with_heartbeat(events)

    def cancel(self, *, agent_id: str, run_id: str, principal_id: str) -> None:
        """请求取消属于当前主体且仍在执行的运行。"""
        self._runtime.cancel(
            agent_id=agent_id,
            run_id=run_id,
            principal_id=principal_id,
        )

    async def with_heartbeat(
        self,
        events: AsyncIterator[AgentEvent],
    ) -> AsyncIterator[AgentEvent]:
        """等待下一业务事件期间按周期产生统一 heartbeat 事件。"""
        iterator = events.__aiter__()
        pending = asyncio.create_task(anext(iterator))
        last_event: AgentEvent | None = None
        try:
            while True:
                done, _ = await asyncio.wait(
                    {pending},
                    timeout=self._heartbeat_seconds,
                )
                if not done:
                    # 事件编号在运行时产生。超时边界上若业务事件已经完成，
                    # 必须先发送该事件，不能插入一个更大序号的心跳造成游标倒退。
                    if pending.done():
                        continue
                    if last_event is not None:
                        heartbeat = self._runtime.heartbeat(last_event)
                        delivered_heartbeat = self._runtime.prepare_delivery(heartbeat)
                        await self._runtime.publish_event(delivered_heartbeat)
                        yield delivered_heartbeat
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    return
                delivered_event = self._runtime.prepare_delivery(event)
                last_event = delivered_event
                await self._runtime.publish_event(delivered_event)
                yield delivered_event
                pending = asyncio.create_task(anext(iterator))
        finally:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            with suppress(Exception):
                await iterator.aclose()
