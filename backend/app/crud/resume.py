"""提供按可信用户主体读取和整体保存的 PostgreSQL CRUD。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert

from app.crud.identity import resolve_user_id
from app.db.database import PostgresDatabase
from app.models.resume import Resume


@dataclass(frozen=True)
class ResumeRecord:
    """与 ORM Session 生命周期隔离的简历记录快照。"""

    content: dict[str, Any]
    style_config: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class PostgresResumeRepository:
    """按可信主体映射限定简历读取和 upsert。"""

    def __init__(self, database: PostgresDatabase) -> None:
        self._database = database

    def get(self, principal_id: str) -> ResumeRecord | None:
        """不创建用户映射地读取主体简历。"""
        with self._database.session_factory() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return None
            row = session.scalar(select(Resume).where(Resume.owner_id == owner_id))
            return _to_record(row) if row is not None else None

    def upsert(
        self,
        principal_id: str,
        *,
        content: dict[str, Any],
        style_config: dict[str, Any],
    ) -> ResumeRecord:
        """在单一事务中建立用户映射并插入或更新其唯一简历。"""
        with self._database.session_factory.begin() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=True,
                id_generator=self._database.id_generator,
            )
            statement = (
                insert(Resume)
                .values(owner_id=owner_id, content=content, style_config=style_config)
                .on_conflict_do_update(
                    index_elements=[Resume.owner_id],
                    set_={
                        "content": content,
                        "style_config": style_config,
                        "updated_at": func.now(),
                    },
                )
            )
            session.execute(statement)
            row = session.scalar(select(Resume).where(Resume.owner_id == owner_id))
            if row is None:
                raise RuntimeError("简历 upsert 后未能读取已保存记录")
            return _to_record(row)

    def update_if_unchanged(
        self,
        principal_id: str,
        *,
        expected_updated_at: datetime,
        content: dict[str, Any],
    ) -> ResumeRecord | None:
        """仅当简历版本未变化时更新内容，避免候选覆盖并发编辑。"""
        with self._database.session_factory.begin() as session:
            owner_id = resolve_user_id(
                session,
                principal_id,
                create=False,
                id_generator=self._database.id_generator,
            )
            if owner_id is None:
                return None
            result = session.execute(
                update(Resume)
                .where(
                    Resume.owner_id == owner_id,
                    Resume.updated_at == expected_updated_at,
                )
                .values(content=content, updated_at=func.now())
            )
            if result.rowcount != 1:
                return None
            row = session.scalar(select(Resume).where(Resume.owner_id == owner_id))
            return _to_record(row) if row is not None else None


def _to_record(row: Resume) -> ResumeRecord:
    """复制 JSONB 和时间字段，避免向上层暴露 ORM 实体。"""
    return ResumeRecord(
        content=dict(row.content),
        style_config=dict(row.style_config),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )
