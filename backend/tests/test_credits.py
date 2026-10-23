"""积分预检、余额缓存更新和终态退款服务测试。"""

import pytest

from agent.constants import COMMON_AGENT
from agent.errors import CreditServiceUnavailableError, InsufficientCreditsError
from agent.persistence.memory import (
    MemoryBilledChatSubmissionStore,
    MemoryConversationStore,
    MemoryMessageStore,
    MemoryRunStore,
)
from agent.schemas.run import RunRecord, RunStatus
from app.credit_constants import CHAT_MESSAGE_CREDIT_COST
from app.crud.credits import CreditBalanceSnapshot
from app.service.credits import CreditApplicationService
from infra.redis_credit_cache import CreditCacheUnavailableError, RedisCreditCache


class _MemoryCreditRepository:
    """隔离积分服务规则的内存仓储替身。"""

    def __init__(self, snapshots: dict[str, CreditBalanceSnapshot]) -> None:
        self.snapshots = snapshots
        self.reads: list[str] = []
        self.refunds: list[str] = []
        self.pages: list[list[CreditBalanceSnapshot]] = []

    def get_snapshot(self, principal_id: str) -> CreditBalanceSnapshot | None:
        self.reads.append(principal_id)
        return self.snapshots.get(principal_id)

    def refund_run(self, run_id: str) -> CreditBalanceSnapshot | None:
        self.refunds.append(run_id)
        return self.snapshots.get("user@example.test")

    def refund_terminal_runs(self, _batch_size: int):
        return []

    def list_snapshots(self, _after_user_id: int, _limit: int):
        return self.pages.pop(0) if self.pages else []


class _MemoryCreditCache:
    """记录余额读取与发布，模拟 Redis 超时或命中。"""

    def __init__(self, value: tuple[int, int] | None = None) -> None:
        self.value = value
        self.unavailable = False
        self.published: list[tuple[str, int, int]] = []

    def get(self, _principal_id: str):
        if self.unavailable:
            raise CreditCacheUnavailableError()
        return self.value

    def publish(self, principal_id: str, balance: int, version: int) -> None:
        if self.unavailable:
            raise CreditCacheUnavailableError()
        self.published.append((principal_id, balance, version))


def _snapshot(balance: int, version: int = 1) -> CreditBalanceSnapshot:
    return CreditBalanceSnapshot("user@example.test", 17, balance, version)


def test_positive_redis_balance_avoids_a_database_read() -> None:
    repository = _MemoryCreditRepository({})
    cache = _MemoryCreditCache((2, 3))

    CreditApplicationService(repository, cache).ensure_can_submit("user@example.test")

    assert repository.reads == []


def test_zero_cache_rechecks_database_and_repairs_a_stale_zero() -> None:
    repository = _MemoryCreditRepository({"user@example.test": _snapshot(4, 8)})
    cache = _MemoryCreditCache((0, 7))

    CreditApplicationService(repository, cache).ensure_can_submit("user@example.test")

    assert repository.reads == ["user@example.test"]
    assert cache.published == [("user@example.test", 4, 8)]


def test_zero_balance_rejects_new_submission() -> None:
    repository = _MemoryCreditRepository({"user@example.test": _snapshot(0)})
    cache = _MemoryCreditCache(None)

    with pytest.raises(InsufficientCreditsError):
        CreditApplicationService(repository, cache).ensure_can_submit("user@example.test")


def test_redis_unavailable_blocks_preflight_with_controlled_error() -> None:
    repository = _MemoryCreditRepository({"user@example.test": _snapshot(100)})
    cache = _MemoryCreditCache()
    cache.unavailable = True

    with pytest.raises(CreditServiceUnavailableError):
        CreditApplicationService(repository, cache).ensure_can_submit("user@example.test")

    assert repository.reads == []


def test_refund_updates_the_cache_from_the_committed_snapshot() -> None:
    repository = _MemoryCreditRepository({"user@example.test": _snapshot(1, 9)})
    cache = _MemoryCreditCache()

    CreditApplicationService(repository, cache).refund_run("123")

    assert repository.refunds == ["123"]
    assert cache.published == [("user@example.test", 1, 9)]


def test_warm_cache_loads_snapshots_in_pages() -> None:
    repository = _MemoryCreditRepository({})
    repository.pages = [[_snapshot(100, 1)], [_snapshot(5, 12)]]
    cache = _MemoryCreditCache()

    CreditApplicationService(repository, cache).warm_cache(batch_size=1)

    assert cache.published == [
        ("user@example.test", 100, 1),
        ("user@example.test", 5, 12),
    ]


def test_redis_credit_key_does_not_include_the_email() -> None:
    captured: dict[str, object] = {}

    class _FakeRedis:
        def eval(self, script, key_count, key, balance, version):
            captured.update(
                script=script,
                key_count=key_count,
                key=key,
                balance=balance,
                version=version,
            )

        def close(self):
            pass

    cache = RedisCreditCache.__new__(RedisCreditCache)
    cache._redis = _FakeRedis()

    cache.publish("user@example.test", 99, 4)

    assert "user@example.test" not in str(captured["key"])
    assert captured["balance"] == 99
    assert captured["version"] == 4
    assert "tonumber(current) > tonumber(ARGV[2])" in str(captured["script"])


def test_memory_submission_refuses_zero_balance_without_writing_chat_rows() -> None:
    conversation_store = MemoryConversationStore()
    message_store = MemoryMessageStore()
    run_store = MemoryRunStore()
    submission_store = MemoryBilledChatSubmissionStore(
        conversation_store=conversation_store,
        message_store=message_store,
        run_store=run_store,
        credit_cost=CHAT_MESSAGE_CREDIT_COST,
    )
    record = _run_record("request-credit-zero", "123", "456")

    with pytest.raises(InsufficientCreditsError):
        submission_store.submit(record, "789", {"blocks": []})

    assert conversation_store.get(record.conversation_id) is None
    assert message_store.messages[record.conversation_id] == []
    assert run_store.get(record.run_id) is None


def test_memory_submission_reuses_same_request_without_second_debit() -> None:
    conversation_store = MemoryConversationStore()
    message_store = MemoryMessageStore()
    run_store = MemoryRunStore()
    submission_store = MemoryBilledChatSubmissionStore(
        conversation_store=conversation_store,
        message_store=message_store,
        run_store=run_store,
        credit_cost=CHAT_MESSAGE_CREDIT_COST,
        balances={"user@example.test": 1},
    )
    first = _run_record("stable-request-id-0001", "123", "456")
    retry = _run_record("stable-request-id-0001", "999", "998")

    submitted, balance, version = submission_store.submit(first, "789", {"blocks": []})
    retried, retry_balance, retry_version = submission_store.submit(
        retry, "997", {"blocks": []}
    )

    assert submitted.run_id == retried.run_id == first.run_id
    assert (balance, version) == (0, 1)
    assert (retry_balance, retry_version) == (0, 1)
    assert len(message_store.messages[first.conversation_id]) == 1
    assert submission_store.event_keys == {f"debit:{first.run_id}"}


def _run_record(request_id: str, conversation_id: str, run_id: str) -> RunRecord:
    """创建带已计算幂等元数据的测试运行。"""
    return RunRecord(
        run_id=run_id,
        conversation_id=conversation_id,
        principal_id="user@example.test",
        status=RunStatus.QUEUED,
        metadata={
            "request_id": request_id,
            "request_hash": "same-payload-hash",
            "input_message_id": "message-id",
        },
        agent=COMMON_AGENT,
    )
