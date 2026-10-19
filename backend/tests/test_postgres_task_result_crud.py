"""任务结果 ORM 写入与更新返回行验证。"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy.dialects import postgresql

from agent.constants import COMMON_AGENT_ID
from agent.errors import ConversationAccessDeniedError
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from app.crud.task_result import PostgresTaskResultStore


class _SessionContext:
    """为同步 ORM 事务提供最小上下文管理器。"""

    def __init__(self, session: Mock) -> None:
        self._session = session

    def __enter__(self) -> Mock:
        return self._session

    def __exit__(self, *_: object) -> None:
        return None


class _SessionFactory:
    """返回指定的 Mock Session，供 CRUD 单元测试使用。"""

    def __init__(self, session: Mock) -> None:
        self._session = session

    def begin(self) -> _SessionContext:
        return _SessionContext(self._session)


def _store(session: Mock) -> PostgresTaskResultStore:
    """创建仅含 CRUD 所需字段的数据库资源替身。"""
    return PostgresTaskResultStore(
        SimpleNamespace(
            session_factory=_SessionFactory(session),
            id_generator=object(),
        )
    )


def _record() -> TaskResultRecord:
    """返回可用于验证 PostgreSQL 写入构造的任务结果。"""
    return TaskResultRecord(
        task_result_id="101",
        agent_id=COMMON_AGENT_ID,
        user_id="user-1",
        conversation_id="202",
        run_id="303",
        message_id=None,
        result_type="smoke",
        generation_status=TaskResultStatus.PENDING,
    )


def test_save_uses_returning_instead_of_unreliable_rowcount() -> None:
    """插入成功时即使驱动 rowcount 为 -1 也能确认保存结果。"""
    session = Mock()
    session.scalar.side_effect = [11, 22]
    result = Mock(rowcount=-1)
    result.scalar_one_or_none.return_value = 101
    session.execute.return_value = result

    _store(session).save(_record())

    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "RETURNING task_results.id" in compiled
    result.scalar_one_or_none.assert_called_once_with()


def test_save_rejects_upsert_when_returning_has_no_row() -> None:
    """冲突记录不属于相同会话上下文时仍拒绝覆盖。"""
    session = Mock()
    session.scalar.side_effect = [11, 22]
    result = Mock(rowcount=-1)
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    with pytest.raises(ConversationAccessDeniedError):
        _store(session).save(_record())


def test_set_status_uses_returning_for_success_result() -> None:
    """状态更新通过 RETURNING 判断是否命中可信用户的结果记录。"""
    session = Mock()
    session.scalar.return_value = 11
    result = Mock(rowcount=-1)
    result.scalar_one_or_none.return_value = 101
    session.execute.return_value = result

    updated = _store(session).set_status(
        "101", "user-1", TaskResultStatus.SUCCEEDED
    )

    assert updated is True
    statement = session.execute.call_args.args[0]
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "RETURNING task_results.id" in compiled


def test_set_status_returns_false_when_returning_has_no_row() -> None:
    """目标结果不存在或不属于当前用户时报告未更新。"""
    session = Mock()
    session.scalar.return_value = 11
    result = Mock(rowcount=-1)
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    assert _store(session).set_status(
        "101", "user-1", TaskResultStatus.SUCCEEDED
    ) is False
