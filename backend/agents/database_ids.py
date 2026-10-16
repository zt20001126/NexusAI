"""业务智能体在关系表中的稳定雪花 ID，与 API 路由代码分开维护。"""

from agent.constants import (
    COMMON_AGENT_ID,
    IMAGE_AGENT_ID,
    LISTING_AGENT_ID,
    LABOR_LAW_AGENT_ID,
    RESEARCH_AGENT_ID,
    LITERATURE_READER_AGENT_ID,
)
from infra.snowflake import SNOWFLAKE_EPOCH_MILLISECONDS


# worker 1022 保留给静态注册的 Agent ID；应用进程使用 0–1021。
_STATIC_AGENT_WORKER_ID = 1_022
_STATIC_AGENT_TIMESTAMP_MS = 1_735_689_600_000


def _static_agent_id(sequence: int) -> int:
    """按固定时间片生成稳定的静态智能体雪花 ID。"""
    elapsed = _STATIC_AGENT_TIMESTAMP_MS - SNOWFLAKE_EPOCH_MILLISECONDS
    return (elapsed << 22) | (_STATIC_AGENT_WORKER_ID << 12) | sequence


AGENT_DATABASE_IDS: dict[str, int] = {
    COMMON_AGENT_ID: _static_agent_id(1),
    IMAGE_AGENT_ID: _static_agent_id(2),
    LISTING_AGENT_ID: _static_agent_id(3),
    RESEARCH_AGENT_ID: _static_agent_id(4),
    LABOR_LAW_AGENT_ID: _static_agent_id(5),
    LITERATURE_READER_AGENT_ID: _static_agent_id(6),
}
AGENT_CODES_BY_DATABASE_ID = {value: key for key, value in AGENT_DATABASE_IDS.items()}


def agent_database_id(agent_code: str) -> int:
    """将 API 使用的智能体代码转换为数据库雪花 ID。"""
    try:
        return AGENT_DATABASE_IDS[agent_code]
    except KeyError:
        raise ValueError(f"未配置智能体数据库 ID：{agent_code}") from None


def agent_code_from_database_id(database_id: int) -> str:
    """将数据库中的智能体雪花 ID 转换回注册代码。"""
    try:
        return AGENT_CODES_BY_DATABASE_ID[database_id]
    except KeyError:
        raise ValueError(f"数据库中出现未注册的智能体 ID：{database_id}") from None
