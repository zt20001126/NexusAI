"""FastAPI 对外接口和 SSE 协议测试。"""

import json
import asyncio
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver

from agent.constants import (
    COMMON_AGENT,
    IMAGE_AGENT,
    LISTING_AGENT,
    RESEARCH_AGENT,
)
from agent.persistence.memory import (
    MemoryAttachmentStore,
    MemoryConversationStore,
    MemoryEventSequence,
    MemoryMessageStore,
    MemoryTaskResultStore,
)
from agent.runner import build_memory_runner
from agent.schemas.run import RunStatus
from agent.streaming.events import AgentEvent, AgentEventType, RunTerminalStatus
from agent.streaming.publisher import EventPublisher
from app.dependencies.auth import get_principal_id
from bootstrap.application import create_app
from app.service.agent import AgentApplicationService
from app.service.conversation import ConversationApplicationService
from app.service.research import ResearchApplicationService
from app.service.task_result import TaskResultApplicationService
from agents.definition import AgentDefinition
from agents.image_agent.constants import IMAGE_AGENT_DESCRIPTION, IMAGE_AGENT_NAME
from agents.image_agent.graph import build_image_agent_graph
from agents.image_agent.providers.result_downloader import ImageResultDownloader
from agents.image_agent.providers.tokenhub_client import TokenHubImageClient
from agents.listing_agent.constants import LISTING_AGENT_DESCRIPTION, LISTING_AGENT_NAME
from agents.listing_agent.graph import build_listing_agent_graph
from agents.research_agent.constants import RESEARCH_AGENT_DESCRIPTION, RESEARCH_AGENT_NAME
from agents.research_agent.graph import build_research_agent_graph
from agents.research_agent.providers.openalex_client import OpenAlexClient
from agents.listing_agent.schemas import ListingImageAnalysis
from agents.registry import (
    COMMON_AGENT_DESCRIPTION,
    COMMON_AGENT_NAME,
    AgentRegistry,
)
from agent.title import ConversationTitleGenerator
from infra.settings import AppSettings
from tests.fake_models import ScriptedToolCallingProvider

TEST_PNG = b"\x89PNG\r\n\x1a\nmock-image-bytes"


class _MemoryAgentEventStore:
    """测试 API 的进程内事件流，模拟 Redis 游标和 end 结束规则。"""

    def __init__(self) -> None:
        self.events: defaultdict[tuple[str, str], list[AgentEvent]] = defaultdict(list)
        self.worker_tasks: dict[str, asyncio.Task[None]] = {}

    def append(self, event: AgentEvent) -> AgentEvent:
        rows = self.events[(event.conversation_id, event.run_id)]
        sequence = len(rows) + 1
        saved = event.model_copy(update={"event_id": f"{sequence}-0", "sequence": sequence})
        rows.append(saved)
        return saved

    def latest_id(self, conversation_id: str, run_id: str) -> str | None:
        rows = self.events[(conversation_id, run_id)]
        return rows[-1].event_id if rows else None

    def last_event(self, conversation_id: str, run_id: str) -> AgentEvent | None:
        rows = self.events[(conversation_id, run_id)]
        return rows[-1] if rows else None

    def last_event_type(self, conversation_id: str, run_id: str) -> AgentEventType | None:
        event = self.last_event(conversation_id, run_id)
        return event.event_type if event else None

    def validate_cursor(
        self,
        conversation_id: str,
        run_id: str,
        after: str | None,
        *,
        allow_missing_at_latest: bool = False,
    ) -> None:
        del allow_missing_at_latest
        latest = self.latest_id(conversation_id, run_id)
        if latest and after and int(after.split("-", 1)[0]) > int(latest.split("-", 1)[0]):
            raise ValueError("cursor is ahead of stream")

    async def listen(
        self,
        *,
        conversation_id: str,
        run_id: str,
        after: str | None,
        terminal_status: str | None = None,
        allow_missing_at_latest: bool = False,
    ) -> AsyncIterator[AgentEvent]:
        del allow_missing_at_latest
        cursor = int((after or "0-0").split("-", 1)[0])
        loop = asyncio.get_running_loop()
        deadline = loop.time() + 10
        heartbeat_at = loop.time() + 0.05
        while True:
            rows = list(self.events[(conversation_id, run_id)])
            pending = [event for event in rows if event.sequence > cursor]
            if pending:
                for event in pending:
                    cursor = event.sequence
                    yield event
                    if event.event_type == AgentEventType.END:
                        return
                continue
            if terminal_status in {"completed", "cancelled", "failed"}:
                return
            worker_task = self.worker_tasks.get(run_id)
            if worker_task is not None and worker_task.done():
                error = worker_task.exception()
                if error is not None:
                    raise error
            now = loop.time()
            if now >= deadline:
                raise TimeoutError(
                    f"test worker produced no end event: run_id={run_id}, events={rows}"
                )
            if now >= heartbeat_at:
                yield AgentEvent(
                    event_id=f"{cursor}-0",
                    event_type=AgentEventType.HEARTBEAT,
                    conversation_id=conversation_id,
                    run_id=run_id,
                    sequence=cursor,
                )
                heartbeat_at = now + 0.05
            await asyncio.sleep(0.005)


class _MemoryAgentTaskQueue:
    """测试用后台队列，在当前事件循环内执行实际 Worker Service。"""

    def __init__(self, event_store: _MemoryAgentEventStore) -> None:
        self.services: dict[str, AgentApplicationService] = {}
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.event_store = event_store

    def register(self, agent: str, service: AgentApplicationService) -> None:
        self.services[agent] = service

    def enqueue(self, agent: str, run_id: str) -> None:
        current_task = self.tasks.get(run_id)
        if current_task is not None and not current_task.done():
            return
        task = asyncio.create_task(self.services[agent].execute_worker(run_id))
        self.tasks[run_id] = task
        self.event_store.worker_tasks[run_id] = task


def _parse_sse_events(body: str) -> list[dict[str, object]]:
    """解析测试响应并校验 SSE 帧头与 JSON 事件字段一致。"""
    events: list[dict[str, object]] = []
    for block in body.replace("\r\n", "\n").split("\n\n"):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            if ": " in line:
                key, value = line.split(": ", 1)
                fields[key] = value
        if "data" not in fields:
            continue
        event = json.loads(fields["data"])
        assert fields.get("id") == event["event_id"]
        assert fields.get("event") == event["event_type"]
        events.append(event)
    return events


class _FixedTitleGenerator:
    """API 测试使用固定标题，避免访问真实模型服务。"""

    async def generate_title(self, first_user_message: str) -> str | None:
        del first_user_message
        return "模型生成的业务标题"


def _test_lifespan(settings: AppSettings, model_provider: ScriptedToolCallingProvider):
    """为 API 测试注入共享内存存储和模拟图片服务。"""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        conversation_store = MemoryConversationStore()
        message_store = MemoryMessageStore()
        title_generator: ConversationTitleGenerator = _FixedTitleGenerator()
        runner = build_memory_runner(
            settings,
            model_provider=model_provider,
            conversation_store=conversation_store,
            message_store=message_store,
            title_generator=title_generator,
        )
        event_sequence = MemoryEventSequence()
        event_store = _MemoryAgentEventStore()
        task_queue = _MemoryAgentTaskQueue(event_store)
        task_result_store = MemoryTaskResultStore()
        attachment_store = MemoryAttachmentStore()

        def image_response(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200,
                    headers={"x-request-id": "test-request"},
                    json={
                        "request_id": "test-request",
                        "model": "hy-image-v3.5-preview",
                        "choices": [{
                            "delta": {
                                "image": {
                                    "url": "https://test.cos.ap-guangzhou.myqcloud.com/result.png",
                                    "width": 1024,
                                    "height": 1024,
                                }
                            }
                        }],
                    },
                )
            return httpx.Response(200, headers={"content-type": "image/png"}, content=TEST_PNG)

        image_transport = httpx.MockTransport(image_response)
        image_graph = build_image_agent_graph(
            MemorySaver(),
            FakeListChatModel(
                responses=[
                    json.dumps(
                        {
                            "intent": "generate_image",
                            "image_prompt": "淘宝商品详情页，突出商品外观、使用场景和材质细节。",
                        },
                        ensure_ascii=False,
                    )
                ]
            ),
            settings,
            TokenHubImageClient(settings, transport=image_transport),
            ImageResultDownloader(
                timeout_seconds=5,
                max_bytes=settings.image_result_max_bytes,
                transport=image_transport,
            ),
            task_result_store,
            attachment_store,
        )
        image_runner = build_memory_runner(
            settings,
            graph=image_graph,
            conversation_store=conversation_store,
            message_store=message_store,
            agent=IMAGE_AGENT,
            task_result_store=task_result_store,
            attachment_store=attachment_store,
            title_generator=title_generator,
        )
        listing_model = FakeListChatModel(
            responses=[
                ListingImageAnalysis(
                    candidate_category="便携水杯",
                    visible_features=["蓝色杯身", "带杯盖"],
                    packaging_text=[],
                    visible_claims=[],
                    uncertain_observations=[],
                ).model_dump_json(),
                json.dumps(
                    {
                        "product_facts": {"商品类别": "便携水杯"},
                        "questions": [
                            {
                                "id": "capacity",
                                "title": "请选择水杯标注的容量。",
                                "type": "SingleChoice",
                                "options": [
                                    {"label": "350 毫升", "description": "水杯标注容量为 350 毫升"},
                                    {"label": "500 毫升", "description": "水杯标注容量为 500 毫升"},
                                    {"label": "750 毫升", "description": "水杯标注容量为 750 毫升"},
                                    {"label": "不确定/暂不提供", "description": "暂时无法确认容量"},
                                ],
                                "allow_custom_input": False,
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                json.dumps(
                    {"product_facts": {"商品类别": "便携水杯"}, "questions": []},
                    ensure_ascii=False,
                ),
                json.dumps(
                    {
                        "schema_version": "1.0",
                        "product_facts": {"商品类别": "便携水杯", "容量": "500 毫升"},
                        "image_analysis": {
                            "candidate_category": "水杯",
                            "visible_features": ["蓝色杯身", "带杯盖"],
                            "packaging_text": [],
                            "visible_claims": [],
                            "uncertain_observations": [],
                        },
                        "versions": [
                            {
                                "version": version,
                                "title": f"便携水杯 500 毫升 蓝色款 {version}",
                                "selling_points": ["便携设计", "蓝色外观", "日常使用"],
                                "description": "蓝色便携水杯，容量为 500 毫升。适合日常使用。",
                                "keywords": ["便携水杯", "蓝色水杯", "日常水杯"],
                                "product_attributes": {"容量": "500 毫升", "颜色": "蓝色"},
                            }
                            for version in (1, 2, 3)
                        ],
                    },
                    ensure_ascii=False,
                ),
            ]
        )
        listing_graph = build_listing_agent_graph(
            MemorySaver(),
            listing_model,
            task_result_store,
            attachment_store,
        )
        listing_runner = build_memory_runner(
            settings,
            graph=listing_graph,
            conversation_store=conversation_store,
            message_store=message_store,
            agent=LISTING_AGENT,
            task_result_store=task_result_store,
            attachment_store=attachment_store,
            title_generator=title_generator,
        )
        research_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "results": [
                        {
                            "id": "https://openalex.org/W123",
                            "title": "A Research Paper",
                            "publication_year": 2024,
                            "publication_date": "2024-05-12",
                            "language": "en",
                            "authorships": [
                                {"author": {"display_name": "Example Author"}}
                            ],
                            "primary_location": {
                                "source": {"display_name": "Example Journal"}
                            },
                            "best_oa_location": {
                                "pdf_url": "https://example.org/paper.pdf"
                            },
                            "abstract_inverted_index": {"Research": [0], "paper": [1]},
                            "doi": "https://doi.org/10.1234/example",
                            "cited_by_count": 7,
                        }
                    ]
                },
            )
        )
        research_graph = build_research_agent_graph(
            MemorySaver(),
            model_provider.create_chat_model(),
            OpenAlexClient(settings, transport=research_transport),
            task_result_store,
            settings.research_max_search_rounds,
        )
        research_runner = build_memory_runner(
            settings,
            graph=research_graph,
            conversation_store=conversation_store,
            message_store=message_store,
            agent=RESEARCH_AGENT,
            task_result_store=task_result_store,
            title_generator=title_generator,
        )
        publisher = EventPublisher(event_sequence, settings.sse_heartbeat_seconds)
        services = {
            COMMON_AGENT: AgentApplicationService(
                runner,
                publisher,
                conversation_store=conversation_store,
                run_store=runner._run_store,
                event_store=event_store,
                task_queue=task_queue,
            ),
            IMAGE_AGENT: AgentApplicationService(
                image_runner,
                publisher,
                conversation_store=conversation_store,
                run_store=image_runner._run_store,
                event_store=event_store,
                task_queue=task_queue,
            ),
            LISTING_AGENT: AgentApplicationService(
                listing_runner,
                publisher,
                conversation_store=conversation_store,
                run_store=listing_runner._run_store,
                event_store=event_store,
                task_queue=task_queue,
            ),
            RESEARCH_AGENT: AgentApplicationService(
                research_runner,
                publisher,
                conversation_store=conversation_store,
                run_store=research_runner._run_store,
                event_store=event_store,
                task_queue=task_queue,
            ),
        }
        for agent, service in services.items():
            task_queue.register(agent, service)
        app.state.settings = settings
        app.state.auth_service = SimpleNamespace(
            get_session_principal=lambda token: (
                "local-development" if token == "test-session" else None
            )
        )
        app.state.agent_registry = AgentRegistry(
            [
                AgentDefinition(COMMON_AGENT, COMMON_AGENT_NAME, COMMON_AGENT_DESCRIPTION, False),
                AgentDefinition(IMAGE_AGENT, IMAGE_AGENT_NAME, IMAGE_AGENT_DESCRIPTION, True),
                AgentDefinition(
                    LISTING_AGENT,
                    LISTING_AGENT_NAME,
                    LISTING_AGENT_DESCRIPTION,
                    True,
                ),
                AgentDefinition(
                    RESEARCH_AGENT,
                    RESEARCH_AGENT_NAME,
                    RESEARCH_AGENT_DESCRIPTION,
                    False,
                ),
            ],
            services,
        )
        app.state.task_result_store = task_result_store
        task_result_service = TaskResultApplicationService(task_result_store)
        app.state.task_result_service = task_result_service
        app.state.research_service = ResearchApplicationService(
            services[RESEARCH_AGENT],
            task_result_service,
        )
        app.state.attachment_store = attachment_store
        app.state.conversation_service = ConversationApplicationService(
            conversation_store,
            message_store,
            task_result_store,
            attachment_store,
        )
        yield

    return lifespan


def _client(settings: AppSettings | None = None) -> TestClient:
    """创建带显式测试生命周期的 API 客户端。"""
    resolved_settings = settings or AppSettings(_env_file=None)
    model_provider = ScriptedToolCallingProvider()
    client = TestClient(
        create_app(
            resolved_settings,
            model_provider=model_provider,
            lifespan=_test_lifespan(resolved_settings, model_provider),
        )
    )
    client.cookies.set(resolved_settings.auth_cookie_name, "test-session")
    return client


def test_common_agent_uses_registered_chat_route() -> None:
    """通用智能体通过注册表路由及其字符串枚举值访问。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-request-id-0001", "message": "帮我整理需求"},
        )

    assert response.status_code == 200
    events = response.json()["data"]
    assert events
    assert all(set(event) == {"event_id", "event_type", "timestamp", "data"} for event in events)


def test_new_chat_requires_a_stable_request_id() -> None:
    """所有收费的新对话提交入口必须显式携带幂等标识。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat/stream",
            json={"message": "这条请求没有幂等标识"},
        )

    assert response.status_code == 422


def test_multi_agent_discovery_includes_research_agent() -> None:
    """公开注册的通用助手、图片助手、Listing 和科研检索智能体。"""
    with _client() as client:
        response = client.get("/api/agents")

    assert response.status_code == 200
    assert [
        (item["agent"], item["name"])
        for item in response.json()["data"]
    ] == [
        (COMMON_AGENT, "通用智能体"),
        (IMAGE_AGENT, "图片智能体"),
        (LISTING_AGENT, "listing生成智能体"),
        (RESEARCH_AGENT, "科研文献检索智能体"),
    ]


def test_research_rest_search_returns_papers_and_reusable_session() -> None:
    """REST 检索返回结构化论文，并允许后续请求复用数字会话 ID。"""
    with _client() as client:
        response = client.post(
            "/api/v1/research/search",
            json={
                "request_id": "test-research-id-0001",
                "message": "查找关于科研方法的论文",
                "limit": 1,
                "year_from": 2020,
                "year_to": 2025,
                "language": "en",
            },
        )
        detail = response.json()["data"]
        history = client.get(f"/api/conversations/{detail['session_id']}/messages")
        assistant_message = next(
            item for item in history.json()["data"]["items"] if item["role"] == "assistant"
        )
        task_result_id = assistant_message["task_results"][0]["task_result_id"]
        stored_result = client.get(f"/api/task-results/{task_result_id}")
        continued = client.post(
            "/api/v1/research/search",
            json={
                "request_id": "test-research-id-0002",
                "message": "查找关于科研方法的论文",
                "session_id": detail["session_id"],
                "limit": 1,
                "year_from": 2020,
                "year_to": 2025,
                "language": "en",
            },
        )
        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        unauthorized = client.get(f"/api/task-results/{task_result_id}")

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert detail["status"] == "success"
    assert detail["returned_count"] == 1
    assert detail["papers"][0]["title"] == "A Research Paper"
    assert detail["session_id"].isdigit()
    assert stored_result.status_code == 200
    assert stored_result.json()["data"]["result_type"] == "research_search"
    assert stored_result.json()["data"]["result_data"]["papers"][0]["doi"] == "10.1234/example"
    assert continued.status_code == 200
    assert continued.json()["data"]["session_id"] == detail["session_id"]
    assert unauthorized.status_code == 404


def test_research_rest_returns_no_results_as_a_business_status() -> None:
    """有效请求无匹配论文时仍返回 HTTP 成功和 no_results 状态。"""
    with _client() as client:
        response = client.post(
            "/api/v1/research/search",
            json={
                "request_id": "test-research-id-0003",
                "message": "查找科研论文",
                "limit": 5,
                "year_from": 2026,
                "year_to": 2026,
            },
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "no_results"
    assert response.json()["data"]["papers"] == []


def test_research_rest_returns_partial_when_fewer_papers_match() -> None:
    """OpenAlex 返回数量低于请求值时保留论文并标记 partial。"""
    with _client() as client:
        response = client.post(
            "/api/v1/research/search",
            json={"request_id": "test-research-id-0004", "message": "查找科研论文", "limit": 5},
        )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "partial"
    assert response.json()["data"]["returned_count"] == 1


def test_stream_chat_uses_stable_sse_contract_without_general_question_cards() -> None:
    """流式接口使用公共事件协议，通用对话澄清仍是普通助手消息。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat/stream",
            json={"request_id": "test-stream-id-0001", "message": "帮我整理需求"},
        )
        history = client.get(
            f"/api/conversations/{response.headers['x-conversation-id']}/messages"
        ).json()["data"]["items"]

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-conversation-id"].isdigit()
    assert response.headers["x-run-id"].isdigit()
    events = _parse_sse_events(response.text)
    assert all(
        set(event) == {"event_id", "event_type", "timestamp", "data"}
        for event in events
    )
    normalized_sse = response.text.replace("\r\n", "\n")
    assert "event: message\n" in normalized_sse
    assert "event: end\n" in normalized_sse
    assert "event: question\n" not in normalized_sse
    completed = next(
        event for event in events
        if event["event_type"] == "message"
        and event["data"].get("operation") == "snapshot"
    )
    assert set(completed) == {"event_id", "event_type", "timestamp", "data"}
    assert completed["data"]["content"]["blocks"][0]["text"] == "你希望整理哪类开发目标？"
    history_message = next(
        message for message in history
        if message["message_id"] == completed["data"]["message_id"]
    )
    assert history_message["content"]["blocks"][0]["id"] == (
        completed["data"]["content"]["blocks"][0]["id"]
    )
    assert history_message["content"]["blocks"][0]["text"] == (
        completed["data"]["content"]["blocks"][0]["text"]
    )
    assert not {"conversation_id", "run_id"}.intersection(completed["data"])


def test_legacy_agent_route_is_not_supported() -> None:
    """固定单智能体接口不会接受 agent 路径参数。"""
    with _client() as client:
        response = client.post(
            "/api/agents/missing/chat",
            json={"request_id": "test-missing-id-0001", "message": "hello"},
        )

    assert response.status_code == 404


def test_unknown_agent_is_a_controlled_not_found() -> None:
    """未知标识不会退回默认图或泄漏内部异常。"""
    with _client() as client:
        response = client.post(
            "/api/agents/not-registered/chat",
            json={"request_id": "test-unknown-id-0001", "message": "开始"},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_AGENT"


def test_conversation_cannot_be_reused_by_another_agent() -> None:
    """同一主体也不能把通用智能体的会话切换到图片图继续执行。"""
    with _client() as client:
        common_response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-agent-id-0001", "message": "创建一个通用智能体会话"},
        )
        conversations = client.get("/api/conversations").json()["data"]["items"]
        conversation_id = conversations[0]["conversation_id"]
        image_response = client.post(
            f"/api/agents/{IMAGE_AGENT}/chat",
            json={
                "request_id": "test-agent-id-0002",
                "message": "帮我生成商品图",
                "conversation_id": conversation_id,
            },
        )

    assert image_response.status_code == 404
    assert image_response.json()["code"] == "CONVERSATION_ACCESS_DENIED"


def test_image_agent_upload_ask_resume_persist_and_authorize_result() -> None:
    """完整走通参考图上传、参数追问、模拟 TokenHub、生图持久化和结果授权。"""
    settings = AppSettings(tokenhub_api_key="unit-test-key", _env_file=None)
    with _client(settings) as client:
        upload = client.post(
            "/api/uploads/images",
            params={"agent": IMAGE_AGENT, "file_name": "../product.png"},
            headers={"Content-Type": "text/plain"},
            content=TEST_PNG,
        )
        attachment_id = upload.json()["data"]["attachment_id"]
        paused_response = client.post(
            f"/api/agents/{IMAGE_AGENT}/chat/stream",
            json={
                "request_id": "test-image-id-0001",
                "message": "生成一个淘宝详情页。",
                "attachment_ids": [attachment_id],
            },
        )
        paused_events = _parse_sse_events(paused_response.text)
        question_event = next(
            event for event in paused_events
            if event["event_type"] == "message"
            and event["data"].get("operation") == "snapshot"
            and any(
                block.get("type") == "question"
                for block in event["data"]["content"]["blocks"]
            )
        )
        conversation_id = paused_response.headers["x-conversation-id"]
        run_id = paused_response.headers["x-run-id"]
        question_block = next(
            block for block in question_event["data"]["content"]["blocks"]
            if block["type"] == "question"
        )
        question_message_id = question_event["data"]["message_id"]
        waiting_end = next(event for event in paused_events if event["event_type"] == "end")
        assert waiting_end["data"]["status"] == "waiting"
        assert "run_id" not in question_block

        resumed = client.post(
            f"/api/agents/{IMAGE_AGENT}/runs/{run_id}/resume",
            json={
                "request_id": "test-resume-id-0001",
                "conversation_id": conversation_id,
                "answers": {"image_size": "1:1 方图（1024×1024）"},
            },
        )
        assert resumed.headers["x-event-cursor"] == waiting_end["event_id"]
        resumed_events = _parse_sse_events(resumed.text)
        result_event = next(
            event
            for event in resumed_events
            if event["event_type"] == "message"
            and event["data"].get("operation") == "snapshot"
            and any(
                block.get("type") == "task_result"
                and block.get("generation_status") == "succeeded"
                for block in event["data"]["content"]["blocks"]
            )
        )
        result_block = next(
            block for block in result_event["data"]["content"]["blocks"]
            if block["type"] == "task_result"
        )
        history = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": 50},
        ).json()["data"]["items"]
        result = next(
            item
            for message in history
            for item in message["task_results"]
        )
        linked_task_results = [
            task_result
            for message in history
            for task_result in message["task_results"]
        ]
        question_message = next(
            item for item in history if item["message_id"] == question_message_id
        )
        user_message = next(item for item in history if item["role"] == "user")
        image_block = next(
            block for block in user_message["content"]["blocks"]
            if block["type"] == "image"
        )
        assert isinstance(image_block["id"], str) and image_block["id"]
        assert image_block["type"] == "image"
        assert image_block["attachment_id"] == attachment_id
        assert image_block["image_url"] == (
            f"/api/conversations/{conversation_id}/messages/"
            f"{user_message['message_id']}/attachments/{attachment_id}/image"
        )
        uploaded_image_response = client.get(image_block["image_url"])
        wrong_message_response = client.get(
            f"/api/conversations/{conversation_id}/messages/"
            f"{next(item['message_id'] for item in history if item['role'] == 'assistant')}"
            f"/attachments/{attachment_id}/image"
        )
        other_upload = client.post(
            "/api/uploads/images",
            params={"agent": IMAGE_AGENT, "file_name": "other.png"},
            content=TEST_PNG,
        )
        wrong_attachment_response = client.get(
            f"/api/conversations/{conversation_id}/messages/{user_message['message_id']}"
            f"/attachments/{other_upload.json()['data']['attachment_id']}/image"
        )
        image_response = client.get(result["image_url"])

        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        unauthorized = client.get(result["image_url"])
        unauthorized_upload = client.get(image_block["image_url"])

    assert upload.status_code == 200
    assert upload.json()["data"]["mime_type"] == "image/png"
    assert upload.json()["data"]["file_name"] == "product.png"
    assert paused_response.status_code == 200
    assert question_block["questions"][0]["id"] == "image_size"
    assert resumed.status_code == 200
    assert result_block["image_url"] == result["image_url"]
    assert len(linked_task_results) == 1, [
        {
            "message_id": item["message_id"],
            "task_result_ids": [result["task_result_id"] for result in item["task_results"]],
        }
        for item in history
        if item["task_results"]
    ]
    assert question_message["task_results"], [
        (item["message_id"], item["role"], item["task_results"], item["content"]["blocks"])
        for item in history
    ]
    assert question_message["task_results"][0]["task_result_id"] == result["task_result_id"]
    assert result["agent"] == IMAGE_AGENT
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content == TEST_PNG
    assert uploaded_image_response.status_code == 200
    assert uploaded_image_response.headers["content-type"] == "image/png"
    assert uploaded_image_response.content == TEST_PNG
    assert wrong_message_response.status_code == 404
    assert wrong_attachment_response.status_code == 404
    assert unauthorized.status_code == 404
    assert unauthorized_upload.status_code == 404


def test_image_upload_rejects_unrecognized_file_content() -> None:
    """上传接口按文件签名拒绝伪装成图片的普通文件。"""
    with _client() as client:
        response = client.post(
            "/api/uploads/images",
            content=b"this is not a png",
            headers={"Content-Type": "image/png"},
        )

    assert response.status_code == 415


def test_listing_chat_requires_at_least_one_product_image() -> None:
    """Listing 路由在运行前拒绝缺少商品图片的任务。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{LISTING_AGENT}/chat",
            json={"request_id": "test-listing-id-0001", "message": "生成商品 Listing"},
        )

    assert response.status_code == 422
    assert "至少上传一张商品图片" in response.json()["detail"]


def test_listing_questions_are_required_and_result_json_is_owner_scoped() -> None:
    """Listing 批量追问后生成三版 JSON，并仅允许任务所有者读取。"""
    with _client() as client:
        upload_response = client.post(
            "/api/uploads/images",
            params={"agent": LISTING_AGENT, "file_name": "cup.png"},
            content=TEST_PNG,
        )
        attachment_id = upload_response.json()["data"]["attachment_id"]
        first_response = client.post(
            f"/api/agents/{LISTING_AGENT}/chat/stream",
            json={
                "request_id": "test-listing-id-0002",
                "message": "这是一款蓝色便携水杯，请帮我写淘宝商品内容。",
                "attachment_ids": [attachment_id],
            },
        )
        first_events = _parse_sse_events(first_response.text)
        question_event = next(
            event for event in first_events
            if event["event_type"] == "message"
            and event["data"].get("operation") == "snapshot"
            and any(
                block.get("type") == "question"
                for block in event["data"]["content"]["blocks"]
            )
        )
        conversation_id = first_response.headers["x-conversation-id"]
        run_id = first_response.headers["x-run-id"]
        question_block = next(
            block for block in question_event["data"]["content"]["blocks"]
            if block["type"] == "question"
        )
        question_message_id = question_event["data"]["message_id"]
        task_result_block = next(
            block for block in question_event["data"]["content"]["blocks"]
            if block["type"] == "task_result"
        )
        question_id = question_block["questions"][0]["id"]
        assert "prompt" not in question_block["questions"][0]
        assert "placeholder" not in question_block["questions"][0]
        assert question_block["questions"][0]["options"][0] == {
            "label": "350 毫升",
            "description": "水杯标注容量为 350 毫升",
        }
        blank_resume = client.post(
            f"/api/agents/{LISTING_AGENT}/runs/{run_id}/resume",
            json={
                "request_id": "test-listing-resume-id-0001",
                "conversation_id": conversation_id,
                "answers": {question_id: "  "},
            },
        )
        resume_response = client.post(
            f"/api/agents/{LISTING_AGENT}/runs/{run_id}/resume",
            json={
                "request_id": "test-listing-resume-id-0002",
                "conversation_id": conversation_id,
                "answers": {question_id: "500 毫升"},
            },
        )
        resumed_events = _parse_sse_events(resume_response.text)
        result_event = next(
            event
            for event in resumed_events
            if event["event_type"] == "message"
            and event["data"].get("operation") == "snapshot"
            and any(
                block.get("type") == "task_result"
                for block in event["data"]["content"]["blocks"]
            )
        )
        result_block = next(
            block for block in result_event["data"]["content"]["blocks"]
            if block["type"] == "task_result"
        )
        task_result_id = result_block["task_result_id"]
        result_response = client.get(f"/api/task-results/{task_result_id}")
        history = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": 50},
        ).json()["data"]["items"]
        linked_task_results = [
            task_result
            for message in history
            for task_result in message["task_results"]
        ]
        question_message = next(
            item for item in history if item["message_id"] == question_message_id
        )
        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        unauthorized_response = client.get(f"/api/task-results/{task_result_id}")

    result_data = result_response.json()["data"]["result_data"]
    assert upload_response.status_code == 200
    assert first_response.status_code == 200
    assert question_block["questions"][0]["id"] == "capacity"
    assert task_result_block["result_type"] == "listing"
    assert task_result_block["task_result_id"] == task_result_id
    assert len(linked_task_results) == 1
    assert question_message["task_results"][0]["task_result_id"] == task_result_id
    assert blank_resume.status_code == 422
    assert resume_response.status_code == 200
    assert result_response.status_code == 200
    assert result_data["schema_version"] == "1.0"
    assert len(result_data["versions"]) == 3
    assert result_data["versions"][0]["description"] == (
        "蓝色便携水杯，容量为 500 毫升。适合日常使用。"
    )
    assert unauthorized_response.status_code == 404


def test_image_upload_enforces_configured_size_limit() -> None:
    """上传流在超过配置上限时及时中止，不把超大文件存入数据库。"""
    settings = AppSettings(image_upload_max_bytes=1_024, _env_file=None)
    with _client(settings) as client:
        response = client.post(
            "/api/uploads/images",
            content=b"\x89PNG\r\n\x1a\n" + b"x" * 1_025,
        )

    assert response.status_code == 413


def test_general_chat_uses_natural_language_without_question_cards() -> None:
    """通用聊天通过助手消息自然澄清，不产生结构化追问事件。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-common-id-0001", "message": "帮我梳理业务"},
        )
        events = response.json()["data"]

    assert response.status_code == 200
    assert not any(
        event["event_type"] == "message"
        and any(
            block.get("type") == "question"
            for block in event["data"].get("content", {}).get("blocks", [])
        )
        for event in events
    )
    completed = next(
        event for event in events
        if event["event_type"] == "message"
        and event["data"].get("operation") == "snapshot"
    )
    assert completed["data"]["content"]["blocks"][0]["text"] == "你希望整理哪类开发目标？"
    terminal_events = [
        event for event in events if event["event_type"] == "end"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0]["data"]["status"] == "completed"


def test_conversation_and_message_history_endpoints_support_paging() -> None:
    """会话列表和消息历史 API 返回新建对话，并可按消息 ID 读取更早消息。"""
    with _client() as client:
        first_response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-history-id-0001", "message": "帮我梳理业务"},
        )
        conversations = client.get("/api/conversations").json()["data"]["items"]
        conversation_id = conversations[0]["conversation_id"]
        second_response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={
                "request_id": "test-history-id-0002",
                "conversation_id": conversation_id,
                "message": "再补充：面向售后工单处理。",
            },
        )
        assert second_response.status_code == 200

        conversations_response = client.get(
            "/api/conversations",
            params={"limit": 10, "offset": 0},
        )
        latest_page_response = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": 2},
        )
        full_history_response = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": 50},
        )
        latest_page = latest_page_response.json()["data"]
        full_history = full_history_response.json()["data"]
        earlier_page_response = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={
                "limit": 2,
                "before_message_id": latest_page["next_before_message_id"],
            },
        )

    conversations = conversations_response.json()["data"]["items"]
    assert conversations_response.status_code == 200
    assert conversations[0]["conversation_id"] == conversation_id
    assert conversations[0]["title"] == "模型生成的业务标题"

    assert latest_page_response.status_code == 200
    assert [item["message_id"] for item in latest_page["items"]] == [
        item["message_id"] for item in full_history["items"][-2:]
    ]
    assert latest_page["next_before_message_id"] == latest_page["items"][0]["message_id"]
    assert any(
        item["role"] == "user"
        and item["content"]["blocks"][0]["text"] == "再补充：面向售后工单处理。"
        for item in full_history["items"]
    )

    earlier_page = earlier_page_response.json()["data"]
    assert earlier_page_response.status_code == 200
    assert [item["message_id"] for item in earlier_page["items"]] == [
        item["message_id"] for item in full_history["items"][-4:-2]
    ], {
        "full_history": [
            (item["message_id"], item["role"], item["created_at"])
            for item in full_history["items"]
        ],
        "cursor": latest_page["next_before_message_id"],
        "earlier_page": [
            (item["message_id"], item["role"], item["created_at"])
            for item in earlier_page["items"]
        ],
    }
    assert not any(
        block["type"] == "question_batch"
        for message in earlier_page["items"]
        for block in message["content"]["blocks"]
    )


def test_conversation_messages_are_hidden_from_other_principals() -> None:
    """消息历史查询必须验证会话归属，且不泄露其他主体是否拥有会话。"""
    with _client() as client:
        chat_response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-owner-id-0001", "message": "创建我的会话"},
        )
        conversations = client.get("/api/conversations").json()["data"]["items"]
        conversation_id = conversations[0]["conversation_id"]
        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        response = client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 404
    assert response.json()["code"] == "CONVERSATION_ACCESS_DENIED"


def test_conversation_query_rejects_invalid_page_sizes() -> None:
    """接口拒绝超出约束的分页参数。"""
    with _client() as client:
        response = client.get("/api/conversations", params={"limit": 101})

    assert response.status_code == 422


def test_resume_rejects_unbounded_answer_text() -> None:
    """HTTP 边界拒绝无界恢复内容，防止超大数据进入图 Checkpoint。"""
    with _client() as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/runs/unknown/resume",
            json={
                "request_id": "test-unbounded-resume-0001",
                "conversation_id": "conversation",
                "answers": {"goal": "x" * 2_001},
            },
        )

    assert response.status_code == 422


def test_cancel_rejects_unknown_run_without_leaking_memory() -> None:
    """取消不存在运行时返回稳定错误，不把伪造标识写入取消集合。"""
    with _client() as client:
        response = client.post(f"/api/agents/{COMMON_AGENT}/runs/123/cancel")

    assert response.status_code == 409
    assert response.json()["code"] == "RUN_NOT_CANCELLABLE"


def test_production_rejects_missing_authenticated_principal() -> None:
    """生产环境不能把匿名调用方静默归并到共享开发身份。"""
    settings = AppSettings(app_env="production", _env_file=None)
    provider = ScriptedToolCallingProvider()
    with TestClient(
        create_app(
            settings,
            model_provider=provider,
            lifespan=_test_lifespan(settings, provider),
        )
    ) as client:
        response = client.post(
            f"/api/agents/{COMMON_AGENT}/chat",
            json={"request_id": "test-production-id-0001", "message": "开始"},
        )

    assert response.status_code == 401
