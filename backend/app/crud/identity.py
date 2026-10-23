"""提供 CRUD 共用的可信主体到内部用户 ID 解析逻辑。"""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.credit import UserCredit
from infra.snowflake import SnowflakeIdGenerator


def resolve_user_id(
    session: Session,
    principal_id: str,
    *,
    create: bool,
    id_generator: SnowflakeIdGenerator,
) -> int | None:
    """查询可信主体的内部 ID；按需安全地创建唯一映射。"""
    user_id = session.scalar(select(User.user_id).where(User.account == principal_id))
    if user_id is None and not create:
        return user_id

    if user_id is None:
        session.execute(
            insert(User)
            .values(
                user_id=id_generator.next_id(),
                account=principal_id,
            )
            .on_conflict_do_nothing(index_elements=[User.account])
        )
        user_id = session.scalar(select(User.user_id).where(User.account == principal_id))
    if user_id is None:
        raise RuntimeError("无法分配数据库用户 ID")
    session.execute(
        insert(UserCredit)
        .values(user_id=user_id, balance=0, version=0)
        .on_conflict_do_nothing(index_elements=[UserCredit.user_id])
    )
    return user_id
