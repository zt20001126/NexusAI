"""智能体基座配置，供 BaseAgent、图构建器和校验节点共同读取。

部署时应根据模型上下文和运行资源设置输入长度及递归步数上限；修改后会影响
所有使用该配置实例构建的图。
"""

from pydantic import BaseModel, ConfigDict, Field

from agent.enums import AgentType

DEFAULT_MAX_INPUT_CHARS = 20_000
DEFAULT_RECURSION_LIMIT = 24


class BaseAgentConfig(BaseModel):
    """定义单个智能体的稳定身份、提示词和执行限制。"""

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    agent: AgentType = Field(description="稳定的智能体类型。")
    system_prompt: str = Field(
        min_length=1,
        description="该智能体使用的系统提示词。",
    )
    max_input_chars: int = Field(
        default=DEFAULT_MAX_INPUT_CHARS,
        gt=0,
        description="单次用户输入允许的最大字符数。",
    )
    recursion_limit: int = Field(
        default=DEFAULT_RECURSION_LIMIT,
        gt=0,
        description="LangGraph 单次运行允许经过的最大节点步数。",
    )
