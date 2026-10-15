"""按稳定业务标识查找智能体定义和运行服务。"""

from collections.abc import Iterable
from typing import Any

from agent.constants import (
    COMMON_AGENT_ID,
    IMAGE_AGENT_ID,
    LISTING_AGENT_ID,
    LABOR_LAW_AGENT_ID,
    RESEARCH_AGENT_ID,
)
from agent.errors import UnknownAgentError
from agents.definition import AgentDefinition
from agents.image_agent.constants import IMAGE_AGENT_DESCRIPTION, IMAGE_AGENT_NAME
from agents.listing_agent.constants import LISTING_AGENT_DESCRIPTION, LISTING_AGENT_NAME
from agents.research_agent.constants import (
    RESEARCH_AGENT_DESCRIPTION,
    RESEARCH_AGENT_NAME,
)
from agents.labor_law_agent.constants import (
    LABOR_LAW_AGENT_DESCRIPTION,
    LABOR_LAW_AGENT_NAME,
)


COMMON_AGENT_NAME = "通用智能体"
COMMON_AGENT_DESCRIPTION = "陪用户自然交流、回答常见问题并介绍项目中的智能体"

# 项目实际注册的智能体目录，供 API 和通用智能体共用，避免两处元数据不一致。
PROJECT_AGENT_DEFINITIONS = (
    AgentDefinition(
        agent_id=COMMON_AGENT_ID,
        name=COMMON_AGENT_NAME,
        description=COMMON_AGENT_DESCRIPTION,
        supports_image_upload=False,
    ),
    AgentDefinition(
        agent_id=IMAGE_AGENT_ID,
        name=IMAGE_AGENT_NAME,
        description=IMAGE_AGENT_DESCRIPTION,
        supports_image_upload=True,
    ),
    AgentDefinition(
        agent_id=LISTING_AGENT_ID,
        name=LISTING_AGENT_NAME,
        description=LISTING_AGENT_DESCRIPTION,
        supports_image_upload=True,
    ),
    AgentDefinition(
        agent_id=RESEARCH_AGENT_ID,
        name=RESEARCH_AGENT_NAME,
        description=RESEARCH_AGENT_DESCRIPTION,
        supports_image_upload=False,
    ),
    AgentDefinition(
        agent_id=LABOR_LAW_AGENT_ID,
        name=LABOR_LAW_AGENT_NAME,
        description=LABOR_LAW_AGENT_DESCRIPTION,
        supports_image_upload=False,
    ),
)


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
