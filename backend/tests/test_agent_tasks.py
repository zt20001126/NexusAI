"""Celery Worker 异常补偿与追问终态幂等测试。"""

from collections import defaultdict

import pytest

from agent.schemas.run import RunRecord, RunStatus
from agent.streaming.events import AgentEvent, AgentEventType, RunTerminalStatus
from agent.persistence.memory import MemoryMessageStore
from app.service import agent_tasks
from infra.settings import AppSettings
from infra.snowflake import get_snowflake_generator


class _MemoryRunStore:
    def __init__(self, record: RunRecord) -> None:
        self.record = record
        self.saved: list[RunStatus] = []

    def get(self, run_id: str) -> RunRecord | None:
        return self.record if self.record.run_id == run_id else None

    def save(self, record: RunRecord) -> None:
        self.record = record
        self.saved.append(record.status)


class _MemoryEventStore:
    def __init__(self) -> None:
        self.events: defaultdict[tuple[str, str], list[AgentEvent]] = defaultdict(list)
        self.closed = False

    def last_event(self, conversation_id: str, run_id: str) -> AgentEvent | None:
        events = self.events[(conversation_id, run_id)]
        return events[-1] if events else None

    def append(self, event: AgentEvent) -> AgentEvent:
        events = self.events[(event.conversation_id, event.run_id)]
        sequence = len(events) + 1
        saved = event.model_copy(update={"event_id": f"{sequence}-0", "sequence": sequence})
        events.append(saved)
        return saved

    async def aclose(self) -> None:
        self.closed = True


class _MemoryDatabase:
    def __enter__(self) -> "_MemoryDatabase":
        return self

    def __exit__(self, *_args: object) -> None:
        return None


class _MemoryCreditRepository:
    """让 Worker 恢复测试显式隔离 PostgreSQL 积分事务。"""

    def __init__(self, _database: _MemoryDatabase) -> None:
        pass

    def refund_run(self, _run_id: str):
        return None


def _patch_recovery_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    record: RunRecord,
    event_store: _MemoryEventStore,
    message_store: MemoryMessageStore,
) -> _MemoryRunStore:
    run_store = _MemoryRunStore(record)
    task_result_links: dict[str, str] = {}

    class _MemoryTaskResultStore:
        def link_message(self, task_result_id: str, message_id: str, _principal_id: str) -> None:
            task_result_links[task_result_id] = message_id

    monkeypatch.setattr(agent_tasks, "PostgresDatabase", lambda *_args: _MemoryDatabase())
    monkeypatch.setattr(agent_tasks, "PostgresRunStore", lambda _database: run_store)
    monkeypatch.setattr(agent_tasks, "PostgresCreditRepository", _MemoryCreditRepository)
    monkeypatch.setattr(agent_tasks, "PostgresMessageStore", lambda _database: message_store)
    monkeypatch.setattr(
        agent_tasks,
        "PostgresTaskResultStore",
        lambda _database: _MemoryTaskResultStore(),
    )
    monkeypatch.setattr(agent_tasks, "RedisAgentEventStore", lambda _settings: event_store)
    monkeypatch.setattr(
        agent_tasks,
        "get_snowflake_generator",
        lambda worker_id: get_snowflake_generator(worker_id),
    )
    return run_store


@pytest.mark.asyncio
async def test_waiting_worker_recovery_persists_question_then_waiting_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Worker 中断后从待答元数据补齐消息快照，再补发 end(waiting)。"""
    record = RunRecord(
        run_id="456",
        conversation_id="123",
        principal_id="owner",
        status=RunStatus.WAITING,
        metadata={
            "question_round_count": 1,
            "pending_questions": [{
                "id": "capacity",
                "title": "请选择容量。",
                "type": "SingleChoice",
                "options": [
                    {"label": f"{size} 毫升", "description": f"{size} 毫升容量"}
                    for size in (350, 500, 750, 1000)
                ],
                "allow_custom_input": False,
            }],
        },
    )
    event_store = _MemoryEventStore()
    message_store = MemoryMessageStore()
    _patch_recovery_dependencies(monkeypatch, record, event_store, message_store)

    await agent_tasks._record_worker_start_failure(
        record.run_id,
        AppSettings(database_url="postgresql+psycopg://user:pass@localhost/nexus", _env_file=None),
    )

    events = event_store.events[(record.conversation_id, record.run_id)]
    assert [event.event_type for event in events] == [AgentEventType.MESSAGE, AgentEventType.END]
    question_message = message_store.list_by_conversation(record.conversation_id, 10, None)[0]
    assert question_message.role == "assistant"
    assert {block["type"] for block in question_message.content["blocks"]} == {"text", "question"}
    assert events[0].data["message_id"] == question_message.message_id
    assert events[1].data == {"status": RunTerminalStatus.WAITING.value}
    assert event_store.closed


@pytest.mark.asyncio
async def test_waiting_worker_recovery_does_not_append_after_waiting_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """补偿重复执行时已有 end(waiting) 就不在其后追加快照或终态。"""
    record = RunRecord(
        run_id="456",
        conversation_id="123",
        principal_id="owner",
        status=RunStatus.WAITING,
    )
    event_store = _MemoryEventStore()
    event_store.append(AgentEvent(
        event_id="",
        event_type=AgentEventType.END,
        conversation_id=record.conversation_id,
        run_id=record.run_id,
        sequence=0,
        data={"status": RunTerminalStatus.WAITING.value},
    ))
    _patch_recovery_dependencies(
        monkeypatch,
        record,
        event_store,
        MemoryMessageStore(),
    )

    await agent_tasks._record_worker_start_failure(
        record.run_id,
        AppSettings(database_url="postgresql+psycopg://user:pass@localhost/nexus", _env_file=None),
    )

    assert [
        event.event_type for event in event_store.events[(record.conversation_id, record.run_id)]
    ] == [AgentEventType.END]
    assert event_store.closed


@pytest.mark.asyncio
async def test_terminal_worker_recovery_emits_failed_end_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """数据库已失败但 Redis 缺少结束事件时只补发一次受控错误。"""
    record = RunRecord(
        run_id="456",
        conversation_id="123",
        principal_id="owner",
        status=RunStatus.FAILED,
    )
    event_store = _MemoryEventStore()
    _patch_recovery_dependencies(
        monkeypatch,
        record,
        event_store,
        MemoryMessageStore(),
    )
    settings = AppSettings(
        database_url="postgresql+psycopg://user:pass@localhost/nexus",
        _env_file=None,
    )

    await agent_tasks._record_worker_start_failure(record.run_id, settings)
    await agent_tasks._record_worker_start_failure(record.run_id, settings)

    events = event_store.events[(record.conversation_id, record.run_id)]
    assert len(events) == 1
    assert events[0].event_type == AgentEventType.END
    assert events[0].data == {
        "status": RunTerminalStatus.FAILED.value,
        "error": {
            "code": "AGENT_WORKER_START_FAILED",
            "message": "智能体暂时无法启动，请稍后重新提交",
        },
    }
