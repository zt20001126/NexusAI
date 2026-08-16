"""连接 HTTP DTO、单智能体运行器与事件发布器。"""

from collections.abc import AsyncIterator
from typing import Any

from agent.runner import AgentRunner
from agent.streaming.events import AgentEvent
from agent.streaming.publisher import EventPublisher


class AgentApplicationService:
    """负责对话、恢复、取消和 SSE 心跳编排。"""

    def __init__(self, runner: AgentRunner, publisher: EventPublisher) -> None:
        """注入唯一智能体运行器和传输事件发布器。"""
        self._runner = runner
        self._publisher = publisher

    async def chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
    ) -> list[AgentEvent]:
        """执行非流式对话并收集完整事件。"""
        events = self._runner.stream_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
        )
        return await self._publisher.publish_all(events)

    def stream_chat(
        self,
        *,
        message: str,
        conversation_id: str | None,
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """执行流式对话，并在图长时间无输出时插入协议级心跳。"""
        events = self._runner.stream_chat(
            message=message,
            conversation_id=conversation_id,
            principal_id=principal_id,
        )
        return self._publisher.with_heartbeat(events)

    def resume(
        self,
        *,
        conversation_id: str,
        run_id: str,
        answers: dict[str, Any],
        principal_id: str,
    ) -> AsyncIterator[AgentEvent]:
        """校验主体后恢复运行，并继续提供协议级心跳。"""
        events = self._runner.resume(
            conversation_id=conversation_id,
            run_id=run_id,
            answers=answers,
            principal_id=principal_id,
        )
        return self._publisher.with_heartbeat(events)

    def cancel(self, *, run_id: str, principal_id: str) -> None:
        """请求取消属于当前主体且仍在执行的运行。"""
        self._runner.cancel(run_id=run_id, principal_id=principal_id)
