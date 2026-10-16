"""验证并集中管理注入到智能体图中的 LangChain 工具。"""

import re
from collections.abc import Iterable

from langchain_core.tools import BaseTool
from pydantic import BaseModel

from agents.base_agent.errors import BaseAgentConfigurationError


TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class ToolRegistry:
    """维护不可变工具集合，并在图构建前检查名称和参数 schema。"""

    def __init__(self, tools: Iterable[BaseTool] = ()) -> None:
        tool_list = tuple(tools)
        names = [tool.name for tool in tool_list]

        if len(names) != len(set(names)):
            raise BaseAgentConfigurationError(
                "工具名称必须唯一",
                code="duplicate_tool_name",
            )

        for tool in tool_list:
            if TOOL_NAME_PATTERN.fullmatch(tool.name) is None:
                raise BaseAgentConfigurationError(
                    "工具名称必须使用小写字母、数字和下划线，且以字母开头",
                    code="invalid_tool_name",
                )
            if not isinstance(tool.description, str) or not tool.description.strip():
                raise BaseAgentConfigurationError(
                    "每个工具都必须提供用途描述",
                    code="missing_tool_description",
                )
            if tool.args_schema is None:
                raise BaseAgentConfigurationError(
                    "每个工具都必须提供参数 schema",
                    code="missing_tool_schema",
                )
            if not isinstance(tool.args_schema, type) or not issubclass(
                tool.args_schema,
                BaseModel,
            ):
                raise BaseAgentConfigurationError(
                    "工具参数 schema 必须使用 Pydantic 模型",
                    code="invalid_tool_schema",
                )

        self._tools = tool_list
        self._tool_names = frozenset(names)

    @property
    def tools(self) -> tuple[BaseTool, ...]:
        """返回只读工具集合，供模型绑定和图节点构建使用。"""

        return self._tools

    @property
    def names(self) -> frozenset[str]:
        """返回已注册工具名称，用于检查模型发起的工具调用。"""

        return self._tool_names
