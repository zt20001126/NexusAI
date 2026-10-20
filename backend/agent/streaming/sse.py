"""AgentEvent 到 SSE 消息的唯一编码边界。"""

from collections.abc import AsyncIterator

from agent.streaming.events import AgentEvent


async def encode_sse_events(
    events: AsyncIterator[AgentEvent],
) -> AsyncIterator[dict[str, str]]:
    """编码命名事件、恢复游标和 JSON 数据，不透传 LangGraph 内部事件。"""
    async for event in events:
        public_event = event.public_event()
        yield {
            "event": public_event.event_type.value,
            "id": public_event.event_id,
            "data": public_event.model_dump_json(),
        }
