"""科研文献检索计划、论文映射和 OpenAlex HTTP 契约测试。"""

import json

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from agent.persistence.memory import MemoryTaskResultStore
from agents.research_agent.graph import build_research_agent_graph
from agents.research_agent.providers.openalex_client import (
    OpenAlexClient,
    OpenAlexError,
)
from agents.research_agent.schemas import ResearchSearchPlan
from agents.research_agent.services.normalizer import (
    deduplicate_papers,
    matches_plan,
    normalize_work,
    reconstruct_abstract,
    sort_papers,
)
from agents.research_agent.tools.search_works import create_research_search_tool
from infra.settings import AppSettings


def _work(
    *,
    work_id: str = "https://openalex.org/W1",
    title: str = "Graph Neural Networks",
    year: int = 2024,
    language: str = "en",
    doi: str | None = "https://doi.org/10.1234/Example",
    citations: int = 8,
) -> dict[str, object]:
    """构造字段齐全的 OpenAlex Work 固定样本。"""
    return {
        "id": work_id,
        "title": title,
        "publication_year": year,
        "publication_date": f"{year}-04-05",
        "language": language,
        "authorships": [{"author": {"display_name": "Ada Researcher"}}],
        "primary_location": {"source": {"display_name": "Example Journal"}},
        "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"},
        "abstract_inverted_index": {"neural": [1], "Graph": [0], "networks": [2]},
        "doi": doi,
        "cited_by_count": citations,
    }


def test_normalizer_reconstructs_abstract_and_maps_openalex_fields() -> None:
    """倒排摘要按词位置还原，作者、来源和 DOI 只取上游字段。"""
    paper = normalize_work(_work())

    assert paper is not None
    assert paper.title == "Graph Neural Networks"
    assert paper.authors == ["Ada Researcher"]
    assert paper.abstract == "Graph neural networks"
    assert paper.doi == "10.1234/example"
    assert paper.language == "en"
    assert paper.paper_url == "https://openalex.org/W1"
    assert paper.pdf_url == "https://example.org/paper.pdf"


def test_normalizer_handles_missing_fields_and_rejects_non_https_links() -> None:
    """可选字段缺失时降级为空值，缺少论文标识或标题时跳过。"""
    invalid_identity = normalize_work({"id": "http://openalex.org/W2", "title": "Title"})
    paper = normalize_work(
        {
            **_work(),
            "best_oa_location": {"pdf_url": "javascript:alert(1)"},
            "abstract_inverted_index": None,
        }
    )

    assert invalid_identity is None
    assert paper is not None
    assert paper.pdf_url is None
    assert paper.abstract is None
    assert reconstruct_abstract({"invalid": "shape"}) is None


def test_hard_filters_deduplication_and_citation_sort_are_deterministic() -> None:
    """检索结果再次按年份和语言硬过滤，再按 DOI 去重和引用量排序。"""
    first = normalize_work(_work(citations=3))
    duplicate = normalize_work(_work(work_id="https://openalex.org/W2", citations=50))
    old = normalize_work(_work(work_id="https://openalex.org/W3", year=2018))
    foreign_language = normalize_work(
        _work(work_id="https://openalex.org/W4", language="fr", doi=None)
    )
    assert first is not None and duplicate is not None
    assert old is not None and foreign_language is not None
    plan = ResearchSearchPlan(
        query="graph neural networks",
        year_from=2020,
        year_to=2025,
        language="en",
    )

    filtered = [
        paper for paper in (first, duplicate, old, foreign_language)
        if matches_plan(paper, plan)
    ]
    unique = deduplicate_papers(filtered)
    sorted_papers = sort_papers(unique, "citation_count")

    assert len(sorted_papers) == 1
    assert sorted_papers[0].citation_count == 3


@pytest.mark.asyncio
async def test_openalex_client_sends_filters_sort_and_optional_bearer_key() -> None:
    """HTTP 请求使用固定 Works 端点、结构化参数和 Authorization Header。"""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"results": [_work()]})

    client = OpenAlexClient(
        AppSettings(
            openalex_api_key="test-key",
            openalex_retry_delay_seconds=0,
            _env_file=None,
        ),
        transport=httpx.MockTransport(handler),
    )
    works = await client.search_works(
        query="graph neural networks",
        per_page=12,
        year_from=2020,
        year_to=2024,
        language="en",
        sort="citation_count",
    )

    assert len(works) == 1
    assert captured[0].url.host == "api.openalex.org"
    assert captured[0].url.path == "/works"
    assert captured[0].url.params["per_page"] == "12"
    assert captured[0].url.params["filter"] == "publication_year:2020-2024,language:en"
    assert captured[0].url.params["sort"] == "cited_by_count:desc"
    assert captured[0].headers["Authorization"] == "Bearer test-key"


@pytest.mark.asyncio
async def test_openalex_client_retries_rate_limit_with_bounded_attempts() -> None:
    """429 响应按配置次数重试，成功后仅返回校验过的 results。"""
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"results": [_work()]})

    client = OpenAlexClient(
        AppSettings(
            openalex_max_retries=1,
            openalex_retry_delay_seconds=0,
            _env_file=None,
        ),
        transport=httpx.MockTransport(handler),
    )

    works = await client.search_works(
        query="graph neural networks",
        per_page=10,
        year_from=None,
        year_to=None,
        language=None,
        sort="relevance",
    )

    assert call_count == 2
    assert len(works) == 1


@pytest.mark.asyncio
async def test_openalex_client_returns_safe_error_after_server_failure() -> None:
    """5xx 超出重试次数后转换为不含原始响应的安全错误。"""
    client = OpenAlexClient(
        AppSettings(openalex_max_retries=0, _env_file=None),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, text="sensitive upstream body")
        ),
    )

    with pytest.raises(OpenAlexError, match="OpenAlex 暂时无法完成检索") as error:
        await client.search_works(
            query="graph neural networks",
            per_page=10,
            year_from=None,
            year_to=None,
            language=None,
            sort="relevance",
        )

    assert "sensitive upstream body" not in str(error.value)


@pytest.mark.asyncio
async def test_search_tool_merges_rounds_and_keeps_papers_out_of_tool_output() -> None:
    """多轮查询合并到同一 task result，工具消息只返回状态和数量。"""

    class _TwoRoundOpenAlex:
        def __init__(self) -> None:
            self.queries: list[str] = []

        async def search_works(self, **kwargs: object) -> list[dict[str, object]]:
            query = str(kwargs["query"])
            self.queries.append(query)
            work_id = "https://openalex.org/W1" if len(self.queries) == 1 else (
                "https://openalex.org/W2"
            )
            return [_work(work_id=work_id, title=query, doi=None)]

    store = MemoryTaskResultStore()
    openalex_client = _TwoRoundOpenAlex()
    search_tool = create_research_search_tool(
        openalex_client=openalex_client,  # type: ignore[arg-type]
        task_result_store=store,
    )
    tool_output = await search_tool.ainvoke(
        {
            "plan": {
                "query": "graph neural networks",
                "alternative_queries": ["graph representation learning"],
            },
            "limit": 2,
            "original_request": "检索图神经网络论文",
            "task_result_id": "123",
            "principal_id": "owner",
            "conversation_id": "456",
            "run_id": "789",
            "agent_id": "research_agent",
            "max_search_rounds": 2,
        }
    )
    record = store.get_owned("123", "owner")

    assert openalex_client.queries == [
        "graph neural networks",
        "graph representation learning",
    ]
    assert record is not None
    assert record.result_data["returned_count"] == 2
    assert record.generation_status.value == "succeeded"
    assert "task_result_id" in str(tool_output)
    assert "graph neural networks" not in str(tool_output)


@pytest.mark.asyncio
async def test_checkpoint_keeps_full_papers_only_in_task_result_store() -> None:
    """图完成后 Checkpoint 只留计划和短摘要，完整论文在任务结果表中。"""
    checkpointer = MemorySaver()
    store = MemoryTaskResultStore()
    plan = ResearchSearchPlan(query="graph neural networks")
    model = FakeListChatModel(responses=[plan.model_dump_json()])
    openalex_client = OpenAlexClient(
        AppSettings(openalex_retry_delay_seconds=0, _env_file=None),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json={"results": [_work()]})
        ),
    )
    graph = build_research_agent_graph(
        checkpointer,
        model,
        openalex_client,
        store,
        max_search_rounds=1,
    )
    config = {"configurable": {"thread_id": "research-checkpoint-boundary"}}
    await graph.ainvoke(
        {
            "messages": [HumanMessage(content="检索图神经网络论文")],
            "original_request": "检索图神经网络论文",
            "research_options": {"limit": 1},
            "agent_id": "research_agent",
            "principal_id": "owner",
            "conversation_id": "456",
            "run_id": "789",
            "task_result_id": "123",
        },
        config=config,
    )
    checkpoint = await graph.aget_state(config)
    stored_result = store.get_owned("123", "owner")

    assert stored_result is not None
    assert stored_result.result_data["papers"][0]["title"] == "Graph Neural Networks"
    assert "Graph Neural Networks" not in str(checkpoint.values["messages"])


@pytest.mark.asyncio
async def test_search_tool_persists_controlled_provider_failure_status() -> None:
    """所有 OpenAlex 查询失败时仍保存业务 failed 状态和安全摘要。"""

    class _FailingOpenAlex:
        async def search_works(self, **kwargs: object) -> list[dict[str, object]]:
            raise OpenAlexError("upstream response details must stay hidden")

    store = MemoryTaskResultStore()
    search_tool = create_research_search_tool(
        openalex_client=_FailingOpenAlex(),  # type: ignore[arg-type]
        task_result_store=store,
    )
    tool_output = await search_tool.ainvoke(
        {
            "plan": {"query": "graph neural networks"},
            "limit": 4,
            "original_request": "检索图神经网络论文",
            "task_result_id": "124",
            "principal_id": "owner",
            "conversation_id": "457",
            "run_id": "790",
            "agent_id": "research_agent",
            "max_search_rounds": 1,
        }
    )
    record = store.get_owned("124", "owner")
    decoded_output = json.loads(str(tool_output))
    event_data = decoded_output["data"]

    assert record is not None
    assert record.result_data["status"] == "failed"
    assert decoded_output["success"] is False
    assert event_data["status"] == "failed"
    assert "upstream response details" not in str(tool_output)
