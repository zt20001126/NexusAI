"""按稳定业务标识查找智能体定义和运行服务。"""

from collections.abc import Iterable
from typing import Any

from agent.errors import UnknownAgentError
from agents.definition import AgentDefinition


DEFAULT_AGENT_ID = "default"
TAOBAO_IMAGE_AGENT_ID = "taobao_image"
LISTING_AGENT_ID = "listing_agent"
DEFAULT_AGENT_NAME = "通用智能体"
DEFAULT_AGENT_DESCRIPTION = "处理常见对话、需求梳理和信息问答"


class AgentRegistry:
    """集中维护已启用智能体的元数据和应用服务。"""

    def __init__(
        self,
        definitions: Iterable[AgentDefinition],
        services: dict[str, Any],
    ) -> None:
        """初始化定义和服务，并拒绝不匹配的注册项。"""
        definition_list = list(definitions)
        self._definitions = {item.agent_id: item for item in definition_list}
        self._services = dict(services)
        if (
            len(self._definitions) != len(definition_list)
            or set(self._definitions) != set(self._services)
        ):
            raise ValueError("智能体定义和运行服务必须一一对应")

    def list_definitions(self) -> list[AgentDefinition]:
        """返回按注册顺序排列的已启用智能体。"""
        return list(self._definitions.values())

    def get_definition(self, agent_id: str) -> AgentDefinition:
        """读取已注册的智能体定义。"""
        definition = self._definitions.get(agent_id)
        if definition is None:
            raise UnknownAgentError()
        return definition

    def get_service(self, agent_id: str) -> Any:
        """读取指定智能体的应用服务。"""
        service = self._services.get(agent_id)
        if service is None:
            raise UnknownAgentError()
        return service
