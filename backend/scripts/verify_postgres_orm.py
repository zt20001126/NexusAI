"""在本机 PostgreSQL 的临时 schema 中验证 ORM CRUD 完整链路。"""

import asyncio
from uuid import uuid4

import psycopg
from psycopg import sql
from sqlalchemy.engine import make_url

from agent.constants import COMMON_AGENT
from agent.errors import RunBusyError
from agent.schemas.run import RunRecord, RunStatus
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from app.crud import (
    PostgresConversationStore,
    PostgresMessageStore,
    PostgresRunLock,
    PostgresRunStore,
    PostgresTaskResultStore,
)
from app.db.database import PostgresDatabase
from infra.settings import AppSettings
from infra.snowflake import SnowflakeIdGenerator


def verify_postgres_orm() -> None:
    """验证 PostgreSQL ORM 写入、读取、授权和互斥锁行为。"""
    settings = AppSettings()
    if settings.database_url is None:
        raise RuntimeError("必须设置 DATABASE_URL 才能运行 PostgreSQL ORM 验证")

    base_url = make_url(settings.database_url)
    if base_url.host not in {"localhost", "127.0.0.1", "::1"}:
        raise RuntimeError("为避免修改远程数据库，验证脚本只允许连接本机 PostgreSQL")

    psycopg_url = base_url.set(drivername="postgresql").render_as_string(
        hide_password=False
    )
    schema = f"codex_orm_smoke_{uuid4().hex}"
    test_url = base_url.set(drivername="postgresql").update_query_dict(
        {"options": [f"-csearch_path={schema}"]}
    ).render_as_string(hide_password=False)

    try:
        with psycopg.connect(psycopg_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema))
            )

        with psycopg.connect(test_url, autocommit=True) as connection:
            active_schema = connection.execute("SELECT current_schema()").fetchone()[0]
            if active_schema != schema:
                raise RuntimeError("PostgreSQL 没有切换到临时隔离 schema")

        id_generator = SnowflakeIdGenerator(settings.snowflake_worker_id)
        with PostgresDatabase(test_url, id_generator) as database:
            conversations = PostgresConversationStore(database)
            messages = PostgresMessageStore(database)
            runs = PostgresRunStore(database)
            results = PostgresTaskResultStore(database)
            run_lock = PostgresRunLock(database)

            conversation_id = id_generator.next_id_string()
            conversations.save(
                conversation_id,
                {"principal_id": "orm-smoke-user", "agent": COMMON_AGENT},
            )
            assert conversations.get(conversation_id) == {
                "principal_id": "orm-smoke-user",
                "agent": COMMON_AGENT,
            }
            conversations.set_title_if_empty(conversation_id, "ORM smoke test")

            run_id = id_generator.next_id_string()
            runs.save(
                RunRecord(
                    run_id=run_id,
                    conversation_id=conversation_id,
                    principal_id="orm-smoke-user",
                    status=RunStatus.WAITING,
                    metadata={"question": "continue"},
                )
            )
            restored_run = runs.get(run_id)
            assert restored_run is not None
            assert restored_run.status is RunStatus.WAITING
            assert restored_run.metadata == {"question": "continue"}
            assert restored_run.agent == COMMON_AGENT

            first_message_id = messages.save(
                conversation_id, run_id, "user", "hello"
            )
            assistant_message_id = messages.save(
                conversation_id, run_id, "assistant", "world"
            )
            history = messages.list_by_conversation(conversation_id, 10, None)
            assert [item.sequence for item in history] == [2, 1]
            assert history[0].message_id == assistant_message_id
            assert history[1].message_id == first_message_id

            task_result_id = id_generator.next_id_string()
            results.save(
                TaskResultRecord(
                    task_result_id=task_result_id,
                    agent=COMMON_AGENT,
                    user_id="orm-smoke-user",
                    conversation_id=conversation_id,
                    run_id=run_id,
                    message_id=None,
                    result_type="smoke",
                    generation_status=TaskResultStatus.PENDING,
                    input_data={"prompt": "hello"},
                    result_data={"ok": True},
                )
            )
            assert results.set_status(
                task_result_id, "orm-smoke-user", TaskResultStatus.SUCCEEDED
            )
            results.link_message(task_result_id, assistant_message_id, "orm-smoke-user")
            owned_result = results.get_owned(task_result_id, "orm-smoke-user")
            assert owned_result is not None
            assert owned_result.message_id == assistant_message_id
            assert owned_result.generation_status is TaskResultStatus.SUCCEEDED
            assert results.get_owned(task_result_id, "different-user") is None
            listed_results = results.list_for_messages(
                conversation_id, [assistant_message_id], "orm-smoke-user"
            )
            assert len(listed_results) == 1
            assert listed_results[0].task_result_id == task_result_id
            assert results.list_for_messages(
                conversation_id, [], "orm-smoke-user"
            ) == []

            listed_conversations = conversations.list_by_owner(
                "orm-smoke-user", 10, 0
            )
            assert len(listed_conversations) == 1
            assert listed_conversations[0].title == "ORM smoke test"

            async def verify_run_lock() -> None:
                await run_lock.acquire(conversation_id)
                try:
                    try:
                        await run_lock.acquire(conversation_id)
                    except RunBusyError:
                        pass
                    else:
                        raise AssertionError("同一会话的重复锁获取未被拒绝")
                finally:
                    await run_lock.release(conversation_id)
                await run_lock.acquire(conversation_id)
                await run_lock.release(conversation_id)

            asyncio.run(verify_run_lock())
    finally:
        with psycopg.connect(psycopg_url, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(
                    sql.Identifier(schema)
                )
            )


if __name__ == "__main__":
    verify_postgres_orm()
    print(
        "PostgreSQL ORM CRUD smoke test passed: identity, conversation, message, "
        "run, task result, and run lock"
    )
