"""提供 CRUD 共用的可信主体到内部用户 ID 解析逻辑。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.identity import UserIdentity
from infra.snowflake import SnowflakeIdGenerator


def resolve_user_id(
    session: Session,
    principal_id: str,
    *,
    create: bool,
    id_generator: SnowflakeIdGenerator,
) -> int | None:
    """查询可信主体的内部 ID；按需安全地创建唯一映射。"""
    user_id = session.scalar(
        select(UserIdentity.user_id).where(
            UserIdentity.external_principal == principal_id
        )
    )
    if user_id is not None or not create:
        return user_id

    session.execute(
        insert(UserIdentity)
        .values(
            user_id=id_generator.next_id(),
            external_principal=principal_id,
        )
        .on_conflict_do_nothing(index_elements=[UserIdentity.external_principal])
    )
    user_id = session.scalar(
        select(UserIdentity.user_id).where(
            UserIdentity.external_principal == principal_id
        )
    )
    if user_id is None:
        raise RuntimeError("无法分配数据库用户 ID")
    return user_id
