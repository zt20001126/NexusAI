"""编排有界 OpenAlex 查询、结果合并和任务结果 upsert。"""

from datetime import datetime, timezone

from agent.persistence.interfaces import TaskResultStore
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agents.research_agent.constants import (
    RESEARCH_AGENT,
    RESEARCH_OPENALEX_SOURCE,
    RESEARCH_RESULT_TYPE,
    RESEARCH_SCHEMA_VERSION,
)
from agents.research_agent.providers.openalex_client import OpenAlexClient, OpenAlexError
from agents.research_agent.schemas import (
    ResearchPaper,
    ResearchSearchResult,
    ResearchSearchToolInput,
    ResearchStatus,
)
from agents.research_agent.services.normalizer import (
    deduplicate_papers,
    matches_plan,
    normalize_work,
    sort_papers,
)


class ResearchSearchService:
    """管理一次 Research 搜索的轮次、合并规则和持久化边界。"""

    def __init__(
        self,
        *,
        openalex_client: OpenAlexClient,
        task_result_store: TaskResultStore,
    ) -> None:
        """注入 OpenAlex 访问能力与共享结果存储协议。"""
        self._openalex_client = openalex_client
        self._task_result_store = task_result_store

    async def search(self, payload: ResearchSearchToolInput) -> ResearchSearchResult:
        """执行计划中的有限查询轮次，并逐轮保存有界标准化候选结果。"""
        queries = _unique_queries(
            [payload.plan.query, *payload.plan.alternative_queries],
            payload.max_search_rounds,
        )
        normalized_candidates: list[ResearchPaper] = []
        attempted_queries: list[str] = []
        request_failed = False
        for query in queries:
            attempted_queries.append(query)
            try:
                works = await self._openalex_client.search_works(
                    query=query,
                    per_page=payload.limit,
                    year_from=payload.plan.year_from,
                    year_to=payload.plan.year_to,
                    language=payload.plan.language,
                    sort=payload.plan.sort.value,
                )
            except OpenAlexError:
                request_failed = True
                if normalized_candidates:
                    break
                continue
            normalized_candidates = self._merge_previous_results(
                normalized_candidates,
                payload,
            )
            for work in works:
                paper = normalize_work(work)
                if paper is not None and matches_plan(paper, payload.plan):
                    normalized_candidates.append(paper)
            normalized_candidates = sort_papers(
                deduplicate_papers(normalized_candidates),
                payload.plan.sort.value,
            )[: payload.limit]
            self._save_task_result(
                payload=payload,
                papers=normalized_candidates,
                status=ResearchStatus.PARTIAL,
                message="检索仍在继续。",
                attempted_queries=attempted_queries,
                generation_status=TaskResultStatus.RUNNING,
            )
            if len(normalized_candidates) >= payload.limit:
                break

        papers = sort_papers(normalized_candidates, payload.plan.sort.value)[: payload.limit]
        status, message = self._result_status(
            papers=papers,
            limit=payload.limit,
            request_failed=request_failed,
        )
        return self._save_task_result(
            payload=payload,
            papers=papers,
            status=status,
            message=message,
            attempted_queries=attempted_queries,
            generation_status=TaskResultStatus.SUCCEEDED,
        )

    def _merge_previous_results(
        self,
        current_papers: list[ResearchPaper],
        payload: ResearchSearchToolInput,
    ) -> list[ResearchPaper]:
        """从同一 task result 读取上一轮候选并按论文标识合并。"""
        existing = self._task_result_store.get_owned(
            payload.task_result_id,
            payload.principal_id,
        )
        if existing is None:
            return current_papers
        saved_papers = existing.result_data.get("papers", [])
        if not isinstance(saved_papers, list):
            return current_papers
        restored: list[ResearchPaper] = []
        for saved_paper in saved_papers:
            if not isinstance(saved_paper, dict):
                continue
            try:
                restored.append(ResearchPaper.model_validate(saved_paper))
            except ValueError:
                continue
        return [*restored, *current_papers]

    def _save_task_result(
        self,
        *,
        payload: ResearchSearchToolInput,
        papers: list[ResearchPaper],
        status: ResearchStatus,
        message: str,
        attempted_queries: list[str],
        generation_status: TaskResultStatus,
    ) -> ResearchSearchResult:
        """把当前有界论文集合 upsert 到当前运行唯一的任务结果记录。"""
        result = ResearchSearchResult(
            schema_version=RESEARCH_SCHEMA_VERSION,
            status=status,
            query=payload.original_request,
            message=message,
            filters={
                "year_from": payload.plan.year_from,
                "year_to": payload.plan.year_to,
                "language": payload.plan.language,
                "sort": payload.plan.sort.value,
                "limit": payload.limit,
                "queries_executed": attempted_queries,
            },
            returned_count=len(papers),
            source=RESEARCH_OPENALEX_SOURCE,
            retrieved_at=datetime.now(timezone.utc),
            papers=papers,
        )
        self._task_result_store.save(
            TaskResultRecord(
                task_result_id=payload.task_result_id,
                agent=RESEARCH_AGENT,
                user_id=payload.principal_id,
                conversation_id=payload.conversation_id,
                run_id=payload.run_id,
                message_id=None,
                result_type=RESEARCH_RESULT_TYPE,
                generation_status=generation_status,
                input_data={
                    "search_plan": payload.plan.model_dump(mode="json"),
                    "queries_executed": attempted_queries,
                },
                result_data=result.model_dump(mode="json"),
            )
        )
        return result

    @staticmethod
    def _result_status(
        *,
        papers: list[ResearchPaper],
        limit: int,
        request_failed: bool,
    ) -> tuple[ResearchStatus, str]:
        """根据完整轮次执行情况生成稳定业务状态和说明。"""
        if request_failed and not papers:
            return ResearchStatus.FAILED, "OpenAlex 暂时无法完成检索，请稍后重试。"
        if not papers:
            return ResearchStatus.NO_RESULTS, "没有找到符合当前条件的论文。"
        if len(papers) < limit:
            return (
                ResearchStatus.PARTIAL,
                f"找到 {len(papers)} 篇符合条件的论文，少于请求的 {limit} 篇。",
            )
        return (
            ResearchStatus.SUCCESS,
            f"找到 {len(papers)} 篇符合条件的论文，完整结果已保存。",
        )


def _unique_queries(queries: list[str], max_rounds: int) -> list[str]:
    """保留等义查询的原始次序并按配置轮数截断。"""
    unique: list[str] = []
    seen: set[str] = set()
    for query in queries:
        normalized = query.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            unique.append(normalized)
            seen.add(key)
        if len(unique) >= max_rounds:
            break
    return unique
