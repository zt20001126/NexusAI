"""FastAPI 对外接口和 SSE 协议测试。"""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langgraph.checkpoint.memory import MemorySaver

from agent.persistence.memory import (
    MemoryAttachmentStore,
    MemoryConversationStore,
    MemoryEventSequence,
    MemoryMessageStore,
    MemoryTaskResultStore,
)
from agent.runner import build_memory_runner
from agent.streaming.publisher import EventPublisher
from app.dependencies.auth import get_principal_id
from app.main import create_app
from app.service.agent import AgentApplicationService
from app.service.conversation import ConversationApplicationService
from app.service.task_result import TaskResultApplicationService
from agents.definition import AgentDefinition
from agents.image_generation.constants import IMAGE_AGENT_DESCRIPTION, IMAGE_AGENT_NAME
from agents.image_generation.graph import build_image_agent_graph
from agents.image_generation.providers.result_downloader import ImageResultDownloader
from agents.image_generation.providers.tokenhub_client import TokenHubImageClient
from agents.listing_agent.constants import LISTING_AGENT_DESCRIPTION, LISTING_AGENT_NAME
from agents.listing_agent.graph import build_listing_agent_graph
from agents.listing_agent.providers.tokenhub_vision import TokenHubVisionClient
from agents.listing_agent.schemas import ListingImageAnalysis
from agents.registry import (
    DEFAULT_AGENT_DESCRIPTION,
    DEFAULT_AGENT_ID,
    DEFAULT_AGENT_NAME,
    LISTING_AGENT_ID,
    TAOBAO_IMAGE_AGENT_ID,
    AgentRegistry,
)
from agent.title import ConversationTitleGenerator
from infra.settings import AppSettings
from tests.fake_models import ScriptedToolCallingProvider

TEST_PNG = b"\x89PNG\r\n\x1a\nmock-image-bytes"


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
            FakeListChatModel(responses=["淘宝商品棚拍主图，柔和自然光，纯净背景。"]),
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
            agent_id=TAOBAO_IMAGE_AGENT_ID,
            task_result_store=task_result_store,
            attachment_store=attachment_store,
            title_generator=title_generator,
        )
        listing_model = FakeListChatModel(
            responses=[
                json.dumps(
                    {
                        "product_facts": {"商品类别": "便携水杯"},
                        "questions": [
                            {
                                "id": "capacity",
                                "title": "商品容量",
                                "prompt": "请确认水杯的实际容量。",
                                "type": "TextQuestion",
                                "allow_custom_input": True,
                                "placeholder": "例如 500 毫升",
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
        listing_settings = AppSettings(
            tokenhub_api_key="test-token",
            image_upload_max_bytes=settings.image_upload_max_bytes,
            _env_file=None,
        )
        vision_payload = ListingImageAnalysis(
            candidate_category="便携水杯",
            visible_features=["蓝色杯身", "带杯盖"],
            packaging_text=[],
            visible_claims=[],
            uncertain_observations=[],
        ).model_dump_json()
        vision_transport = httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={"choices": [{"message": {"content": vision_payload}}]},
            )
        )
        listing_graph = build_listing_agent_graph(
            MemorySaver(),
            listing_model,
            TokenHubVisionClient(listing_settings, transport=vision_transport),
            task_result_store,
            attachment_store,
        )
        listing_runner = build_memory_runner(
            settings,
            graph=listing_graph,
            conversation_store=conversation_store,
            message_store=message_store,
            agent_id=LISTING_AGENT_ID,
            task_result_store=task_result_store,
            attachment_store=attachment_store,
            title_generator=title_generator,
        )
        publisher = EventPublisher(event_sequence, settings.sse_heartbeat_seconds)
        services = {
            DEFAULT_AGENT_ID: AgentApplicationService(runner, publisher),
            TAOBAO_IMAGE_AGENT_ID: AgentApplicationService(image_runner, publisher),
            LISTING_AGENT_ID: AgentApplicationService(listing_runner, publisher),
        }
        app.state.settings = settings
        app.state.agent_service = services[DEFAULT_AGENT_ID]
        app.state.agent_registry = AgentRegistry(
            [
                AgentDefinition(DEFAULT_AGENT_ID, DEFAULT_AGENT_NAME, DEFAULT_AGENT_DESCRIPTION, False),
                AgentDefinition(TAOBAO_IMAGE_AGENT_ID, IMAGE_AGENT_NAME, IMAGE_AGENT_DESCRIPTION, True),
                AgentDefinition(
                    LISTING_AGENT_ID,
                    LISTING_AGENT_NAME,
                    LISTING_AGENT_DESCRIPTION,
                    True,
                ),
            ],
            services,
        )
        app.state.task_result_store = task_result_store
        app.state.task_result_service = TaskResultApplicationService(task_result_store)
        app.state.attachment_store = attachment_store
        app.state.conversation_service = ConversationApplicationService(
            conversation_store,
            message_store,
            task_result_store,
        )
        yield

    return lifespan


def _client(settings: AppSettings | None = None) -> TestClient:
    """创建带显式测试生命周期的 API 客户端。"""
    resolved_settings = settings or AppSettings(_env_file=None)
    model_provider = ScriptedToolCallingProvider()
    return TestClient(
        create_app(
            resolved_settings,
            model_provider=model_provider,
            lifespan=_test_lifespan(resolved_settings, model_provider),
        )
    )


def test_single_agent_uses_fixed_chat_route() -> None:
    """单智能体模板使用固定路由，不要求调用方理解或提交 agent_id。"""
    with _client() as client:
        response = client.post(
            "/api/agent/chat",
            json={"message": "帮我整理需求"},
        )

    assert response.status_code == 200


def test_multi_agent_discovery_includes_listing_agent() -> None:
    """公开注册的通用助手、淘宝图片助手和 Listing 智能体。"""
    with _client() as client:
        response = client.get("/api/agents")

    assert response.status_code == 200
    assert [item["agent_id"] for item in response.json()["data"]] == [
        DEFAULT_AGENT_ID,
        TAOBAO_IMAGE_AGENT_ID,
        LISTING_AGENT_ID,
    ]


def test_stream_chat_uses_stable_sse_event_contract() -> None:
    """流式接口发布命名事件和 JSON 数据，不透传 LangGraph 原始事件。"""
    with _client() as client:
        response = client.post(
            "/api/agent/chat/stream",
            json={"message": "帮我整理需求"},
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: question.required" in response.text
    assert "event: run.completed" not in response.text
    data_lines = [
        line.removeprefix("data: ")
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    events = [json.loads(line) for line in data_lines]
    question = next(event for event in events if event["event_type"] == "question.required")
    assert question["data"]["questions"][0]["id"] == "goal"


def test_legacy_agent_id_route_is_not_supported() -> None:
    """固定单智能体接口不会接受 agent_id 路径参数。"""
    with _client() as client:
        response = client.post(
            "/api/agents/missing/chat",
            json={"message": "hello"},
        )

    assert response.status_code == 404


def test_unknown_agent_is_a_controlled_not_found() -> None:
    """未知标识不会退回默认图或泄漏内部异常。"""
    with _client() as client:
        response = client.post(
            "/api/agents/not-registered/chat",
            json={"message": "开始"},
        )

    assert response.status_code == 404
    assert response.json()["code"] == "UNKNOWN_AGENT"


def test_conversation_cannot_be_reused_by_another_agent() -> None:
    """同一主体也不能把默认智能体的会话切换到图片图继续执行。"""
    with _client() as client:
        default_response = client.post(
            "/api/agent/chat",
            json={"message": "创建一个默认会话"},
        )
        conversation_id = default_response.json()["data"][0]["conversation_id"]
        image_response = client.post(
            f"/api/agents/{TAOBAO_IMAGE_AGENT_ID}/chat",
            json={
                "message": "帮我生成商品图",
                "conversation_id": conversation_id,
            },
        )

    assert image_response.status_code == 409
    assert image_response.json()["code"] == "CONVERSATION_ACCESS_DENIED"


def test_image_agent_upload_ask_resume_persist_and_authorize_result() -> None:
    """完整走通参考图上传、参数追问、模拟 TokenHub、生图持久化和结果授权。"""
    settings = AppSettings(tokenhub_api_key="unit-test-key", _env_file=None)
    with _client(settings) as client:
        upload = client.post(
            "/api/uploads/images",
            params={"agent_id": TAOBAO_IMAGE_AGENT_ID, "file_name": "../product.png"},
            headers={"Content-Type": "text/plain"},
            content=TEST_PNG,
        )
        attachment_id = upload.json()["data"]["attachment_id"]
        paused_response = client.post(
            f"/api/agents/{TAOBAO_IMAGE_AGENT_ID}/chat/stream",
            json={
                "message": "帮我生成一张淘宝商品主图",
                "attachment_ids": [attachment_id],
            },
        )
        paused_events = [
            json.loads(line.removeprefix("data: "))
            for line in paused_response.text.splitlines()
            if line.startswith("data: ")
        ]
        question_event = next(
            event for event in paused_events if event["event_type"] == "question.required"
        )
        conversation_id = question_event["conversation_id"]
        run_id = question_event["run_id"]

        resumed = client.post(
            f"/api/agents/{TAOBAO_IMAGE_AGENT_ID}/runs/{run_id}/resume",
            json={
                "conversation_id": conversation_id,
                "answers": {"image_size": "1:1 方图（1024×1024）"},
            },
        )
        resumed_events = [
            json.loads(line.removeprefix("data: "))
            for line in resumed.text.splitlines()
            if line.startswith("data: ")
        ]
        result_event = next(
            event
            for event in resumed_events
            if event["event_type"] == "task_result.updated"
            and event["data"]["generation_status"] == "succeeded"
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
        image_response = client.get(result["image_url"])

        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        unauthorized = client.get(result["image_url"])

    assert upload.status_code == 200
    assert upload.json()["data"]["mime_type"] == "image/png"
    assert upload.json()["data"]["file_name"] == "product.png"
    assert paused_response.status_code == 200
    assert question_event["data"]["questions"][0]["id"] == "image_size"
    assert resumed.status_code == 200
    assert result_event["data"]["image_url"] == result["image_url"]
    assert result["agent_id"] == TAOBAO_IMAGE_AGENT_ID
    assert image_response.status_code == 200
    assert image_response.headers["content-type"] == "image/png"
    assert image_response.content == TEST_PNG
    assert unauthorized.status_code == 404


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
            f"/api/agents/{LISTING_AGENT_ID}/chat",
            json={"message": "生成商品 Listing"},
        )

    assert response.status_code == 422
    assert "至少上传一张商品图片" in response.json()["detail"]


def test_listing_questions_are_required_and_result_json_is_owner_scoped() -> None:
    """Listing 批量追问后生成三版 JSON，并仅允许任务所有者读取。"""
    with _client() as client:
        upload_response = client.post(
            "/api/uploads/images",
            params={"agent_id": LISTING_AGENT_ID, "file_name": "cup.png"},
            content=TEST_PNG,
        )
        attachment_id = upload_response.json()["data"]["attachment_id"]
        first_response = client.post(
            f"/api/agents/{LISTING_AGENT_ID}/chat",
            json={
                "message": "这是一款蓝色便携水杯，请帮我写淘宝商品内容。",
                "attachment_ids": [attachment_id],
            },
        )
        first_events = first_response.json()["data"]
        question_event = next(
            event for event in first_events if event["event_type"] == "question.required"
        )
        task_result_event = next(
            event for event in first_events if event["event_type"] == "task_result.updated"
        )
        question_id = question_event["data"]["questions"][0]["id"]
        blank_resume = client.post(
            f"/api/agents/{LISTING_AGENT_ID}/runs/{question_event['run_id']}/resume",
            json={
                "conversation_id": question_event["conversation_id"],
                "answers": {question_id: "  "},
            },
        )
        resume_response = client.post(
            f"/api/agents/{LISTING_AGENT_ID}/runs/{question_event['run_id']}/resume",
            json={
                "conversation_id": question_event["conversation_id"],
                "answers": {question_id: "500 毫升"},
            },
        )
        resumed_events = [
            json.loads(line.removeprefix("data: "))
            for line in resume_response.text.splitlines()
            if line.startswith("data: ")
        ]
        result_event = next(
            event
            for event in resumed_events
            if event["event_type"] == "task_result.updated"
        )
        task_result_id = result_event["data"]["task_result_id"]
        result_response = client.get(f"/api/task-results/{task_result_id}")
        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        unauthorized_response = client.get(f"/api/task-results/{task_result_id}")

    result_data = result_response.json()["data"]["result_data"]
    assert upload_response.status_code == 200
    assert first_response.status_code == 200
    assert question_event["data"]["questions"][0]["id"] == "capacity"
    assert task_result_event["data"]["result_type"] == "listing"
    assert task_result_event["data"]["task_result_id"] == task_result_id
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


def test_resume_endpoint_completes_paused_run() -> None:
    """API 调用方可以使用追问事件中的标识恢复并完成同一次运行。"""
    with _client() as client:
        paused_response = client.post(
            "/api/agent/chat",
            json={"message": "帮我梳理业务"},
        )
        paused_events = paused_response.json()["data"]
        question = next(
            event for event in paused_events if event["event_type"] == "question.required"
        )
        resumed_response = client.post(
            f"/api/agent/runs/{question['run_id']}/resume",
            json={
                "conversation_id": question["conversation_id"],
                "answers": {"goal": "构建售后工单智能体"},
            },
        )

    assert resumed_response.status_code == 200
    assert "event: tool.completed" in resumed_response.text
    assert resumed_response.text.count("event: run.completed") == 1
    assert "售后工单智能体" in resumed_response.text


def test_conversation_and_message_history_endpoints_support_paging() -> None:
    """会话列表和消息历史 API 返回新建对话，并可按序号读取更早消息。"""
    with _client() as client:
        paused_response = client.post(
            "/api/agent/chat",
            json={"message": "帮我梳理业务"},
        )
        paused_events = paused_response.json()["data"]
        question = next(
            event for event in paused_events if event["event_type"] == "question.required"
        )
        conversation_id = question["conversation_id"]

        resumed_response = client.post(
            f"/api/agent/runs/{question['run_id']}/resume",
            json={
                "conversation_id": conversation_id,
                "answers": {"goal": "构建售后工单智能体"},
            },
        )
        assert resumed_response.status_code == 200

        conversations_response = client.get(
            "/api/conversations",
            params={"limit": 10, "offset": 0},
        )
        latest_page_response = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={"limit": 2},
        )
        latest_page = latest_page_response.json()["data"]
        earlier_page_response = client.get(
            f"/api/conversations/{conversation_id}/messages",
            params={
                "limit": 2,
                "before_sequence": latest_page["next_before_sequence"],
            },
        )

    conversations = conversations_response.json()["data"]["items"]
    assert conversations_response.status_code == 200
    assert conversations[0]["conversation_id"] == conversation_id
    assert conversations[0]["title"] == "模型生成的业务标题"

    assert latest_page_response.status_code == 200
    assert [item["role"] for item in latest_page["items"]] == ["user", "assistant"]
    assert "构建售后工单智能体" in latest_page["items"][0]["content"]
    assert latest_page["next_before_sequence"] == 3

    earlier_page = earlier_page_response.json()["data"]
    assert earlier_page_response.status_code == 200
    assert [item["sequence"] for item in earlier_page["items"]] == [1, 2]
    assert [item["role"] for item in earlier_page["items"]] == ["user", "assistant"]


def test_conversation_messages_are_hidden_from_other_principals() -> None:
    """消息历史查询必须验证会话归属，且不泄露其他主体是否拥有会话。"""
    with _client() as client:
        chat_response = client.post(
            "/api/agent/chat",
            json={"message": "创建我的会话"},
        )
        event = chat_response.json()["data"][0]
        conversation_id = event["conversation_id"]
        client.app.dependency_overrides[get_principal_id] = lambda: "another-principal"
        response = client.get(f"/api/conversations/{conversation_id}/messages")

    assert response.status_code == 409
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
            "/api/agent/runs/unknown/resume",
            json={
                "conversation_id": "conversation",
                "answers": {"goal": "x" * 2_001},
            },
        )

    assert response.status_code == 422


def test_cancel_rejects_unknown_run_without_leaking_memory() -> None:
    """取消不存在运行时返回稳定错误，不把伪造标识写入取消集合。"""
    with _client() as client:
        response = client.post("/api/agent/runs/123/cancel")

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
        response = client.post("/api/agent/chat", json={"message": "开始"})

    assert response.status_code == 401
