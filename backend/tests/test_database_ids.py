"""验证智能体代码改名后仍映射到原有稳定数据库 ID。"""

import pytest

from agent.constants import COMMON_AGENT_ID, IMAGE_AGENT_ID, LISTING_AGENT_ID
from agent.runner import AgentRunner
from agent.schemas.run import RunRecord, RunStatus
from agents.database_ids import agent_code_from_database_id, agent_database_id


@pytest.mark.parametrize(
    ("agent_code", "database_id"),
    [
        (COMMON_AGENT_ID, 132_633_958_813_786_113),
        (IMAGE_AGENT_ID, 132_633_958_813_786_114),
        (LISTING_AGENT_ID, 132_633_958_813_786_115),
    ],
)
def test_standard_agent_codes_keep_stable_database_ids(
    agent_code: str,
    database_id: int,
) -> None:
    """改名后的 API 代码保持数据库雪花 ID 不变，并能反向解析。"""
    assert agent_database_id(agent_code) == database_id
    assert agent_code_from_database_id(database_id) == agent_code


@pytest.mark.parametrize(
    ("agent_code", "checkpoint_name"),
    [
        (COMMON_AGENT_ID, "default"),
        (IMAGE_AGENT_ID, "taobao_image"),
        (LISTING_AGENT_ID, LISTING_AGENT_ID),
    ],
)
def test_standard_agent_codes_keep_existing_checkpoint_namespaces(
    agent_code: str,
    checkpoint_name: str,
) -> None:
    """智能体改名后继续使用原 Checkpoint 线程键以恢复历史会话。"""
    record = RunRecord(
        run_id="1",
        conversation_id="2",
        principal_id="owner",
        status=RunStatus.RUNNING,
        agent_id=agent_code,
    )

    assert AgentRunner._scope_key(record) == f"owner:{checkpoint_name}:2"
