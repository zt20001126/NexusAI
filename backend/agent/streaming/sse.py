"""AgentEvent 到 SSE 消息的唯一编码边界。"""

from collections.abc import AsyncIterator

from agent.streaming.events import AgentEvent


async def encode_sse_events(
    events: AsyncIterator[AgentEvent],
) -> AsyncIterator[dict[str, str]]:
    """编码命名事件、恢复游标和 JSON 数据，不透传 LangGraph 内部事件。"""
    async for event in events:
        yield {
            "event": event.event_type.value,
            "id": event.event_id,
            "data": event.model_dump_json(),
        }
