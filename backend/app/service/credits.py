"""编排 Redis 预检、积分余额展示、缓存刷新和终态退款。"""

import logging

from agent.errors import CreditServiceUnavailableError, InsufficientCreditsError
from app.credit_constants import CHAT_MESSAGE_CREDIT_COST
from app.crud.credits import CreditBalanceSnapshot, PostgresCreditRepository
from infra.redis_credit_cache import CreditCacheUnavailableError, RedisCreditCache

logger = logging.getLogger(__name__)


class CreditApplicationService:
    """协调积分数据库事实、Redis 快速检查与幂等退款。"""

    def __init__(
        self,
        repository: PostgresCreditRepository,
        cache: RedisCreditCache,
    ) -> None:
        """注入持久仓储与 Redis 缓存适配器。"""
        self._repository = repository
        self._cache = cache

    def ensure_can_submit(self, principal_id: str) -> None:
        """检查新对话余额；缓存缺失或为零时用数据库复核并回填。"""
        try:
            cached = self._cache.get(principal_id)
        except CreditCacheUnavailableError:
            raise CreditServiceUnavailableError() from None
        if cached is not None and cached[0] >= CHAT_MESSAGE_CREDIT_COST:
            return

        snapshot = self._repository.get_snapshot(principal_id)
        if snapshot is None or snapshot.balance < CHAT_MESSAGE_CREDIT_COST:
            raise InsufficientCreditsError()
        self.publish_snapshot(snapshot)

    def get_balance(self, principal_id: str) -> int:
        """从数据库读取账号栏余额，并将准确快照回写到 Redis。"""
        snapshot = self._repository.get_snapshot(principal_id)
        if snapshot is None:
            return 0
        self.publish_snapshot(snapshot)
        return snapshot.balance

    def publish_balance(self, principal_id: str, balance: int, version: int) -> None:
        """提交事务后更新缓存；Redis 临时故障不回滚已经提交的账务。"""
        try:
            self._cache.publish(principal_id, balance, version)
        except CreditCacheUnavailableError:
            logger.warning("credit cache publish failed principal_id=%s", principal_id)

    def publish_snapshot(self, snapshot: CreditBalanceSnapshot) -> None:
        """将数据库返回的确定余额版本发布到缓存。"""
        self.publish_balance(snapshot.principal_id, snapshot.balance, snapshot.version)

    def refresh(self, principal_id: str) -> int:
        """读取数据库当前快照并刷新 Redis，返回持久化余额。"""
        snapshot = self._repository.get_snapshot(principal_id)
        if snapshot is None:
            return 0
        self.publish_snapshot(snapshot)
        return snapshot.balance

    def refund_run(self, run_id: str) -> CreditBalanceSnapshot | None:
        """对失败或取消的运行执行幂等退款并更新缓存。"""
        snapshot = self._repository.refund_run(run_id)
        if snapshot is not None:
            self.publish_snapshot(snapshot)
        return snapshot

    def warm_cache(self, batch_size: int = 500) -> None:
        """先补偿终态退款，再分页预热所有用户余额。"""
        while True:
            snapshots = self._repository.refund_terminal_runs(batch_size)
            for snapshot in snapshots:
                self.publish_snapshot(snapshot)
            if len(snapshots) < batch_size:
                break

        last_user_id = 0
        while True:
            snapshots = self._repository.list_snapshots(last_user_id, batch_size)
            if not snapshots:
                return
            for snapshot in snapshots:
                self._cache.publish(
                    snapshot.principal_id,
                    snapshot.balance,
                    snapshot.version,
                )
            last_user_id = snapshots[-1].user_id
            if len(snapshots) < batch_size:
                return
