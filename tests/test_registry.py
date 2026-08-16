"""智能体注册中心公共契约测试。"""

import pytest

from agent_core.contracts.agent import AgentDefinition
from agent_core.errors import AgentAlreadyRegisteredError, AgentNotFoundError
from agent_core.registry import AgentRegistry


def _placeholder_graph_factory(checkpointer: object) -> object:
    """返回测试占位图，避免注册契约测试依赖 LangGraph 实现。"""
    return checkpointer


def test_registry_can_register_and_resolve_agent() -> None:
    """开发者注册智能体后，可以按稳定标识获取同一份定义。"""
    registry = AgentRegistry()
    definition = AgentDefinition(
        agent_id="example",
        name="示例智能体",
        description="验证注册契约",
        graph_factory=_placeholder_graph_factory,
    )

    registry.register(definition)

    assert registry.get("example") is definition
    assert registry.list_definitions() == [definition]


def test_registry_rejects_duplicate_agent_id() -> None:
    """重复标识会被明确拒绝，防止后注册智能体静默覆盖前者。"""
    registry = AgentRegistry()
    definition = AgentDefinition(
        agent_id="example",
        name="示例智能体",
        description="验证重复注册",
        graph_factory=_placeholder_graph_factory,
    )
    registry.register(definition)

    with pytest.raises(AgentAlreadyRegisteredError) as error:
        registry.register(definition)

    assert error.value.code == "AGENT_ALREADY_REGISTERED"


def test_registry_returns_stable_error_for_unknown_agent() -> None:
    """不存在的智能体返回稳定业务错误，而不是泄露内部 KeyError。"""
    registry = AgentRegistry()

    with pytest.raises(AgentNotFoundError) as error:
        registry.get("missing")

    assert error.value.code == "AGENT_NOT_FOUND"

