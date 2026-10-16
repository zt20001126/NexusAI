"""负责基座依赖注入、图生命周期和输入输出边界的智能体门面。"""

import logging
from collections.abc import Iterable, Mapping
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import BaseTool
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import ValidationError

from agents.base_agent.config import BaseAgentConfig
from agents.base_agent.errors import (
    BaseAgentConfigurationError,
    BaseAgentExecutionError,
    BaseAgentInputError,
)
from agents.base_agent.graph import build_agent_graph
from agents.base_agent.schemas import AgentRequest, AgentResponse
from agents.base_agent.tools.registry import ToolRegistry


logger = logging.getLogger(__name__)


class BaseAgent:
    """基座公开调用入口；模型、工具和 Checkpointer 均由组合方注入。"""

    def __init__(
        self,
        *,
        config: BaseAgentConfig,
        chat_model: BaseChatModel,
        tools: Iterable[BaseTool] = (),
        checkpointer: BaseCheckpointSaver[Any] | None = None,
    ) -> None:
        self._config = config
        self._checkpointer = checkpointer
        self._tool_registry = ToolRegistry(tools)
        self._graph = build_agent_graph(
            config=config,
            chat_model=chat_model,
            tool_registry=self._tool_registry,
            checkpointer=checkpointer,
        )

    @property
    def compiled_graph(self) -> CompiledStateGraph[Any, Any, Any, Any]:
        """返回已编译图，供平台 Runner 等外层适配器接入。"""

        return self._graph

    @property
    def tool_registry(self) -> ToolRegistry:
        """返回只读工具注册表，便于启动诊断和能力展示。"""

        return self._tool_registry

    async def ainvoke(
        self,
        request: AgentRequest | str | Mapping[str, Any],
        *,
        runnable_config: RunnableConfig | None = None,
    ) -> AgentResponse:
        """校验单轮输入，执行图并返回不暴露内部状态的标准响应。"""

        try:
            normalized_request = (
                request
                if isinstance(request, AgentRequest)
                else AgentRequest.model_validate(
                    {"message": request} if isinstance(request, str) else request
                )
            )
        except ValidationError:
            raise BaseAgentInputError(
                "智能体输入格式无效",
                code="invalid_agent_request",
            ) from None

        if len(normalized_request.message) > self._config.max_input_chars:
            raise BaseAgentInputError(
                "用户消息超过允许的长度",
                code="input_too_long",
            )

        graph_config = self._prepare_runnable_config(runnable_config)
        try:
            result = await self._graph.ainvoke(
                {"messages": [HumanMessage(content=normalized_request.message)]},
                config=graph_config,
            )
        except (BaseAgentInputError, BaseAgentExecutionError):
            raise
        except Exception as error:
            logger.warning(
                "智能体执行失败 agent_id=%s error_type=%s",
                self._config.agent_id,
                type(error).__name__,
            )
            raise BaseAgentExecutionError(
                "智能体执行失败",
                code="agent_execution_failed",
            ) from None

        answer = result.get("answer")
        if not isinstance(answer, str) or not answer.strip():
            raise BaseAgentExecutionError(
                "智能体未生成有效回答",
                code="missing_agent_answer",
            )
        return AgentResponse(agent_id=self._config.agent_id, answer=answer)

    def _prepare_runnable_config(
        self,
        runnable_config: RunnableConfig | None,
    ) -> RunnableConfig:
        """合并执行限制和可选线程上下文，不覆盖调用方显式设置。"""

        prepared: dict[str, Any] = dict(runnable_config or {})
        configurable = dict(prepared.get("configurable") or {})
        if self._checkpointer is not None and not configurable.get("thread_id"):
            raise BaseAgentConfigurationError(
                "启用 Checkpointer 时必须提供 configurable.thread_id",
                code="missing_thread_id",
            )
        if configurable:
            prepared["configurable"] = configurable
        prepared.setdefault("recursion_limit", self._config.recursion_limit)

        metadata = dict(prepared.get("metadata") or {})
        metadata.setdefault("agent_id", self._config.agent_id)
        prepared["metadata"] = metadata
        return prepared
