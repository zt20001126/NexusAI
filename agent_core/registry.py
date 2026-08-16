"""进程内智能体注册中心。"""

from threading import RLock

from agent_core.contracts.agent import AgentDefinition
from agent_core.errors import AgentAlreadyRegisteredError, AgentNotFoundError


class AgentRegistry:
    """保存业务智能体定义并提供确定性查询顺序。"""

    def __init__(self) -> None:
        """初始化空注册表；锁只保护注册表本身，不承担会话并发控制。"""
        self._definitions: dict[str, AgentDefinition] = {}
        self._lock = RLock()

    def register(self, definition: AgentDefinition) -> None:
        """注册智能体；重复标识会失败，禁止静默覆盖已有业务。"""
        with self._lock:
            if definition.agent_id in self._definitions:
                raise AgentAlreadyRegisteredError(definition.agent_id)
            self._definitions[definition.agent_id] = definition

    def get(self, agent_id: str) -> AgentDefinition:
        """按标识获取智能体定义，不暴露内部字典异常。"""
        with self._lock:
            definition = self._definitions.get(agent_id)
        if definition is None:
            raise AgentNotFoundError(agent_id)
        return definition

    def list_definitions(self) -> list[AgentDefinition]:
        """按注册顺序返回定义快照，调用方无法修改内部注册表。"""
        with self._lock:
            return list(self._definitions.values())

