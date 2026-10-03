"""事件断点重放入口。"""

from collections.abc import AsyncIterator

from agent.persistence.interfaces import EventBus
from agent.streaming.events import AgentEvent


class EventReplay:
    """把重放能力与具体 Redis 或内存实现隔离。"""

    def __init__(self, event_bus: EventBus) -> None:
        """注入事件总线。"""
        self._event_bus = event_bus

    def subscribe(
        self,
        conversation_id: str,
        after: str | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """从可选游标之后重放，再订阅后续事件。"""
        return self._event_bus.subscribe(conversation_id, after)
