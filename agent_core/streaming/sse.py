"""将 AgentEvent 编码为 sse-starlette 可发送的数据。"""

from collections.abc import AsyncIterator

from agent_core.contracts.events import AgentEvent


async def encode_sse_events(
    events: AsyncIterator[AgentEvent],
) -> AsyncIterator[dict[str, str]]:
    """编码命名事件、恢复游标和 JSON 数据，不透传图内部事件。"""
    async for event in events:
        yield {
            "event": event.event_type.value,
            "id": event.event_id,
            "data": event.model_dump_json(),
        }

