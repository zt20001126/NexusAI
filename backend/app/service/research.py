"""复用统一智能体运行器执行检索，并组装专用 REST 响应。"""

from typing import Any

from agent.streaming.events import AgentEventType
from app.schemas.research import ResearchRequest, ResearchResponse
from app.service.agent import AgentApplicationService
from app.service.task_result import TaskResultApplicationService
from agents.research_agent.schemas import ResearchSearchResult, ResearchStatus


class ResearchApplicationService:
    """协调 Research Agent、任务结果仓储和 API DTO。"""

    def __init__(
        self,
        agent_service: AgentApplicationService,
        task_result_service: TaskResultApplicationService,
    ) -> None:
        """注入注册表中的 Research Agent 服务和结果查询服务。"""
        self._agent_service = agent_service
        self._task_result_service = task_result_service

    async def search(
        self,
        *,
        payload: ResearchRequest,
        principal_id: str,
    ) -> ResearchResponse:
        """执行一次检索；结构化条件作为可信图上下文注入。"""
        options: dict[str, Any] = {"limit": payload.limit}
        for field_name in ("year_from", "year_to", "language"):
            value = getattr(payload, field_name)
            if value is not None:
                options[field_name] = value
        if payload.sort is not None:
            options["sort"] = payload.sort.value
        events = await self._agent_service.chat(
            message=payload.message,
            conversation_id=payload.session_id,
            principal_id=principal_id,
            graph_context={"research_options": options},
        )
        conversation_id = next(
            (event.conversation_id for event in events),
            payload.session_id,
        )
        if conversation_id is None:
            raise RuntimeError("Research Agent 未返回会话标识")
        task_result_id = next(
            (
                event.data.get("task_result_id")
                for event in events
                if event.event_type == AgentEventType.TASK_RESULT_UPDATED
                and isinstance(event.data.get("task_result_id"), str)
            ),
            None,
        )
        if task_result_id is not None:
            detail = self._task_result_service.get_research_result(
                task_result_id=task_result_id,
                principal_id=principal_id,
            )
            if detail is not None:
                result = ResearchSearchResult.model_validate(detail.result_data)
                return ResearchResponse(
                    session_id=conversation_id,
                    status=result.status,
                    query=result.query,
                    papers=result.papers,
                    returned_count=result.returned_count,
                    message=result.message,
                )

        failure_message = next(
            (
                event.data.get("message")
                for event in events
                if event.event_type == AgentEventType.RUN_FAILED
                and isinstance(event.data.get("message"), str)
            ),
            "科研文献检索未能完成，请稍后重试。",
        )
        return ResearchResponse(
            session_id=conversation_id,
            status=ResearchStatus.FAILED,
            query=payload.message,
            papers=[],
            returned_count=0,
            message=failure_message,
        )
