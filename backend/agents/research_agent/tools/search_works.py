"""将可信运行上下文传递给科研文献检索应用服务。"""

from typing import Any

from langchain_core.tools import tool

from agent.persistence.interfaces import TaskResultStore
from agent.schemas.task_result import TaskResultStatus
from agent.schemas.tool_result import ToolResult
from agents.research_agent.constants import RESEARCH_RESULT_TYPE, RESEARCH_TOOL_NAME
from agents.research_agent.providers.openalex_client import OpenAlexClient
from agents.research_agent.schemas import ResearchSearchToolInput, ResearchStatus
from agents.research_agent.services.search import ResearchSearchService


def create_research_search_tool(
    *,
    openalex_client: OpenAlexClient,
    task_result_store: TaskResultStore,
):
    """注入 OpenAlex 和共享任务结果仓储，创建图可调用的搜索工具。"""
    search_service = ResearchSearchService(
        openalex_client=openalex_client,
        task_result_store=task_result_store,
    )

    @tool(RESEARCH_TOOL_NAME, args_schema=ResearchSearchToolInput)
    async def search_openalex_works(
        plan: dict[str, Any],
        limit: int,
        original_request: str,
        task_result_id: str,
        principal_id: str,
        conversation_id: str,
        run_id: str,
        agent_id: str,
        max_search_rounds: int,
    ) -> str:
        """检索 OpenAlex 并返回状态摘要；完整论文只写入任务结果表。"""
        payload = ResearchSearchToolInput.model_validate(
            {
                "plan": plan,
                "limit": limit,
                "original_request": original_request,
                "task_result_id": task_result_id,
                "principal_id": principal_id,
                "conversation_id": conversation_id,
                "run_id": run_id,
                "agent_id": agent_id,
                "max_search_rounds": max_search_rounds,
            }
        )
        result = await search_service.search(payload)
        return ToolResult(
            success=result.status != ResearchStatus.FAILED,
            data={
                "status": result.status.value,
                "returned_count": result.returned_count,
                "message": result.message,
                "task_result": {
                    "task_result_id": payload.task_result_id,
                    "agent_id": payload.agent_id,
                    "result_type": RESEARCH_RESULT_TYPE,
                    "generation_status": TaskResultStatus.SUCCEEDED.value,
                },
            },
            message=result.message,
        ).model_dump_json()

    return search_openalex_works
