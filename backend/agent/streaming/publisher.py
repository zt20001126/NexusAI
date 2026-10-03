"""事件序号、发布和心跳编排。"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import datetime, timezone

from agent.persistence.interfaces import EventBus, EventSequence
from agent.streaming.events import AgentEvent, AgentEventType


class EventPublisher:
    """为实际交付事件分配单调游标，并保存到可替换事件总线。"""

    def __init__(
        self,
        event_bus: EventBus,
        event_sequence: EventSequence,
        heartbeat_seconds: float,
    ) -> None:
        """注入事件存储、序号生成器和心跳周期。"""
        self._event_bus = event_bus
        self._event_sequence = event_sequence
        self._heartbeat_seconds = heartbeat_seconds

    async def publish_all(
        self,
        events: AsyncIterator[AgentEvent],
    ) -> list[AgentEvent]:
        """发布并收集一次非流式调用的全部事件。"""
        return [event async for event in self.with_heartbeat(events, heartbeat=False)]

    async def with_heartbeat(
        self,
        events: AsyncIterator[AgentEvent],
        *,
        heartbeat: bool = True,
    ) -> AsyncIterator[AgentEvent]:
        """发布业务事件，并在流式等待期间插入协议级心跳。"""
        iterator = events.__aiter__()
        pending = asyncio.create_task(anext(iterator))
        last_event: AgentEvent | None = None
        try:
            while True:
                timeout = self._heartbeat_seconds if heartbeat else None
                done, _ = await asyncio.wait({pending}, timeout=timeout)
                if not done:
                    if pending.done():
                        continue
                    if last_event is not None:
                        delivered = await self._deliver(
                            AgentEvent(
                                event_id=last_event.event_id,
                                event_type=AgentEventType.HEARTBEAT,
                                conversation_id=last_event.conversation_id,
                                run_id=last_event.run_id,
                                sequence=last_event.sequence,
                                timestamp=datetime.now(timezone.utc),
                                data={},
                            )
                        )
                        yield delivered
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    return
                delivered = await self._deliver(event)
                last_event = delivered
                yield delivered
                pending = asyncio.create_task(anext(iterator))
        finally:
            if not pending.done():
                pending.cancel()
                with suppress(asyncio.CancelledError):
                    await pending
            with suppress(Exception):
                await iterator.aclose()

    async def _deliver(self, event: AgentEvent) -> AgentEvent:
        """在真正发送前分配游标，保证心跳与业务事件严格单调。"""
        sequence = self._event_sequence.next(event.conversation_id)
        delivered = event.model_copy(
            update={"event_id": f"{event.conversation_id}:{sequence}", "sequence": sequence}
        )
        await self._event_bus.publish(delivered)
        return delivered
