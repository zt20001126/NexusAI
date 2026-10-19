"""图片智能体参数策略和 TokenHub 边界的离线测试。"""

import base64
import json

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agent.constants import IMAGE_AGENT
from agent.errors import AttachmentAccessDeniedError
from agent.persistence.memory import MemoryAttachmentStore, MemoryTaskResultStore
from agent.schemas.task_result import TaskResultRecord, TaskResultStatus
from agents.image_agent.nodes.ask_node import ask_node
from agents.image_agent.nodes.chat_node import create_chat_node
from agents.image_agent.nodes.validation_node import validation_node
from agents.image_agent.parameter_policy import (
    RESIZE_PIXEL_CHOICES,
    SIZE_CHOICES,
    apply_answers,
    extract_documented_options,
)
from agents.image_agent.providers.result_downloader import ImageResultDownloader
from agents.image_agent.providers.tokenhub_client import (
    TokenHubImageClient,
    TokenHubImageError,
)
from agents.image_agent.schemas import ImageGenerationOptions
from infra.settings import AppSettings


@pytest.mark.parametrize(
    ("user_message", "model_intent", "expected"),
    [
        (
            "我想把刚才上传的商品做成适合手机浏览的长版介绍页。",
            "generate_image",
            True,
        ),
        ("图片智能体可以生成淘宝详情页吗？", "other", False),
    ],
)
@pytest.mark.asyncio
async def test_chat_node_uses_model_semantic_intent(
    user_message: str,
    model_intent: str,
    expected: bool,
) -> None:
    """语义分类应区分隐含生图请求和能力咨询，而不是按关键词决定。"""
    model = FakeListChatModel(
        responses=[
            json.dumps(
                {
                    "intent": model_intent,
                    "image_prompt": "手机端竖版商品介绍页，保留参考商品外观。"
                    if expected
                    else "",
                },
                ensure_ascii=False,
            )
        ]
    )
    chat_node = create_chat_node(model)

    result = await chat_node(
        {
            "original_request": user_message,
            "attachment_ids": ["reference-image-1"],
            "run_id": "run-1",
        }
    )

    assert result["is_image_generation"] is expected
    assert result["intent_validated"] is True
    if expected:
        assert result["image_prompt"] == "手机端竖版商品介绍页，保留参考商品外观。"


@pytest.mark.asyncio
async def test_validation_node_clears_previous_intent_for_new_run() -> None:
    """新运行清除上一轮的判断，由聊天模型重新识别本轮语义。"""
    result = await validation_node(
        {
            "original_request": "  这个商品适合什么详情页风格？  ",
            "run_id": "run-2",
            "intent_validated": True,
            "validated_run_id": "run-1",
            "is_image_generation": True,
            "image_prompt": "旧提示词",
            "generation_options": {"size": "1024x1024"},
        }
    )

    assert result["original_request"] == "这个商品适合什么详情页风格？"
    assert result["intent_validated"] is False
    assert result["is_image_generation"] is False
    assert result["image_prompt"] == ""
    assert result["generation_options"] == {}


@pytest.mark.parametrize(
    ("user_text", "expected"),
    [
        ("生成主图，比例 1:1", {"size": "1024x1024", "use_search_tool": False}),
        ("生成商品图，4K，seed=21", {
            "size": "4096x4096",
            "seed": 21,
            "use_search_tool": False,
        }),
        ("生成详情页图，1.5K", {
            "generate_max_pixels": 2_359_296,
            "use_search_tool": False,
        }),
    ],
)
def test_extract_only_documented_image_parameters(user_text: str, expected: dict[str, object]) -> None:
    """自然语言提取只产生 TokenHub 支持的参数，不臆造数量或清晰度字段。"""
    result = extract_documented_options(user_text)

    assert result == expected
    assert "count" not in result
    assert "quality" not in result


def test_extract_explicit_reference_resize_parameter() -> None:
    """用户显式提到文档参数时解析其参考图面积值。"""
    assert extract_documented_options("生成主图，参考图缩放像素=1500000")["resize_max_pixels"] == 1_500_000


def test_image_size_and_pixel_area_are_mutually_exclusive() -> None:
    """尺寸与面积档位只允许设置一项，且宽高遵守文档边界。"""
    with pytest.raises(ValueError):
        ImageGenerationOptions(size="1024x1024", generate_max_pixels=1_048_576).validate_parameter_exclusivity()
    with pytest.raises(ValueError):
        ImageGenerationOptions(size="128x128")
    with pytest.raises(ValueError):
        ImageGenerationOptions(generate_max_pixels=10_000)


@pytest.mark.asyncio
async def test_tokenhub_request_contains_reference_and_documented_options() -> None:
    """TokenHub 请求使用 data URI 传参考图并按文档序列化可选字段。"""
    captured: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(
            200,
            json={
                "request_id": "request-123",
                "model": "hy-image-v3.5-preview",
                "choices": [{
                    "delta": {"image": {"url": "https://result.cos.ap-guangzhou.myqcloud.com/a.png"}}
                }],
            },
        )

    settings = AppSettings(tokenhub_api_key="private-key", _env_file=None)
    client = TokenHubImageClient(settings, transport=httpx.MockTransport(respond))
    result = await client.generate(
        prompt="商品正面展示",
        reference_images=[("image/png", b"reference-image")],
        options=ImageGenerationOptions(
            size="1024x1024",
            resize_max_pixels=2_359_296,
            seed=21,
            footnote="新品",
            use_search_tool=True,
        ),
        session_id="conversation-1",
    )

    body = captured["body"]
    assert captured["authorization"] == "Bearer private-key"
    assert body["model"] == "hy-image-v3.5-preview"
    assert body["session"] == "conversation-1"
    assert body["size"] == "1024x1024"
    assert body["resize_max_pixels"] == 2_359_296
    assert body["seed"] == 21
    assert body["footnote"] == "新品"
    assert body["use_search_tool"] == {"value": True}
    assert body["messages"][0]["content"][0]["text"] == "商品正面展示"
    reference_uri = body["messages"][0]["content"][1]["image_url"]["url"]
    assert reference_uri == f"data:image/png;base64,{base64.b64encode(b'reference-image').decode()}"
    assert result.request_id == "request-123"


@pytest.mark.asyncio
async def test_tokenhub_applies_documented_default_reference_resize_limit() -> None:
    """含参考图但没有覆盖值时发送 TokenHub 文档默认 1K 缩放上限。"""
    captured_body: dict[str, object] = {}

    def respond(request: httpx.Request) -> httpx.Response:
        captured_body.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"delta": {"image": {"url": "https://result.cos.myqcloud.com/a.png"}}}]},
        )

    client = TokenHubImageClient(
        AppSettings(tokenhub_api_key="private-key", _env_file=None),
        transport=httpx.MockTransport(respond),
    )
    await client.generate(
        prompt="商品图",
        reference_images=[("image/png", b"reference")],
        options=ImageGenerationOptions(size="1024x1024"),
        session_id="conversation-1",
    )

    assert captured_body["resize_max_pixels"] == 1_048_576


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected_code"),
    [
        (401, "TOKENHUB_AUTH_FAILED"),
        (422, "TOKENHUB_CONTENT_REJECTED"),
        (429, "TOKENHUB_RATE_LIMITED"),
        (503, "TOKENHUB_UNAVAILABLE"),
    ],
)
async def test_tokenhub_http_errors_are_mapped_without_upstream_body(
    status_code: int,
    expected_code: str,
) -> None:
    """上游状态码映射为稳定错误，原始响应正文不进入对外错误。"""
    settings = AppSettings(tokenhub_api_key="private-key", _env_file=None)
    client = TokenHubImageClient(
        settings,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(status_code, text="secret-provider-detail")
        ),
    )

    with pytest.raises(TokenHubImageError) as raised:
        await client.generate(
            prompt="商品图",
            reference_images=[],
            options=ImageGenerationOptions(size="1024x1024"),
            session_id="conversation-1",
        )

    assert raised.value.code == expected_code
    assert "secret-provider-detail" not in raised.value.public_message


@pytest.mark.asyncio
async def test_tokenhub_rejects_malformed_success_response() -> None:
    """成功状态但缺少最终图片载荷时返回受控格式错误。"""
    client = TokenHubImageClient(
        AppSettings(tokenhub_api_key="private-key", _env_file=None),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"choices": []})),
    )

    with pytest.raises(TokenHubImageError) as raised:
        await client.generate(
            prompt="商品图",
            reference_images=[],
            options=ImageGenerationOptions(size="1024x1024"),
            session_id="conversation-1",
        )

    assert raised.value.code == "TOKENHUB_INVALID_RESPONSE"


@pytest.mark.asyncio
async def test_tokenhub_missing_key_fails_before_network_request() -> None:
    """未配置 TokenHub 密钥时返回受控配置错误且不发送网络请求。"""
    called = False

    def unexpected_request(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    client = TokenHubImageClient(
        AppSettings(_env_file=None),
        transport=httpx.MockTransport(unexpected_request),
    )

    with pytest.raises(TokenHubImageError) as raised:
        await client.generate(
            prompt="商品图",
            reference_images=[],
            options=ImageGenerationOptions(size="1024x1024"),
            session_id="conversation-1",
        )

    assert raised.value.code == "TOKENHUB_NOT_CONFIGURED"
    assert called is False


@pytest.mark.asyncio
async def test_downloader_limits_result_hosts_types_and_size() -> None:
    """结果下载器限制云存储域名、图片 MIME 与最大字节数。"""
    downloader = ImageResultDownloader(
        timeout_seconds=5,
        max_bytes=8,
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "image/png"},
                content=b"123456789",
            )
        ),
    )

    with pytest.raises(TokenHubImageError) as invalid_host:
        await downloader.download("http://127.0.0.1/private.png")
    assert invalid_host.value.code == "IMAGE_RESULT_URL_REJECTED"

    with pytest.raises(TokenHubImageError) as too_large:
        await downloader.download("https://result.cos.ap-guangzhou.myqcloud.com/a.png")
    assert too_large.value.code == "IMAGE_RESULT_TOO_LARGE"


def test_ask_answers_only_map_to_documented_options() -> None:
    """追问答案映射到文档字段，选项使用常见尺寸和像素档位。"""
    answer = next(iter(SIZE_CHOICES))
    options = apply_answers({}, {"image_size": answer, "unlisted_parameter": "ignore"})

    assert options["size"] == SIZE_CHOICES[answer]["size"]
    assert "unlisted_parameter" not in options

    resize_answer = next(iter(RESIZE_PIXEL_CHOICES))
    resized = apply_answers({}, {"resize_max_pixels": resize_answer})
    assert resized["resize_max_pixels"] == RESIZE_PIXEL_CHOICES[resize_answer]["resize_max_pixels"]


@pytest.mark.asyncio
async def test_ask_node_splits_four_questions_and_preserves_prior_answers() -> None:
    """图片参数超过每轮上限时分批询问，并在恢复后保留已确认值。"""
    state = {
        "original_request": "生成商品图，加水印，并提供 seed 以便复现和参考图缩放像素。",
        "attachment_ids": ["attachment-1"],
    }

    first_turn = await ask_node(state)
    first_call = first_turn["messages"][0].tool_calls[0]  # type: ignore[union-attr]
    assert [question["id"] for question in first_call["args"]["questions"]] == [
        "image_size",
        "footnote",
        "seed",
    ]
    assert first_turn["image_size_confirmed"] is False

    size_answer = next(iter(SIZE_CHOICES))
    first_answers = {
        "image_size": size_answer,
        "footnote": "Nexus",
        "seed": "42",
    }
    second_turn = await ask_node(
        {
            **state,
            "generation_options": first_turn["generation_options"],
            "image_size_confirmed": first_turn["image_size_confirmed"],
            "resume_answers": first_answers,
        }
    )
    second_call = second_turn["messages"][0].tool_calls[0]  # type: ignore[union-attr]
    assert [question["id"] for question in second_call["args"]["questions"]] == [
        "resize_max_pixels",
    ]
    assert second_turn["image_size_confirmed"] is True
    assert second_turn["generation_options"]["footnote"] == "Nexus"  # type: ignore[index]
    assert second_turn["generation_options"]["seed"] == 42  # type: ignore[index]

    resize_answer = next(iter(RESIZE_PIXEL_CHOICES))
    third_turn = await ask_node(
        {
            **state,
            "generation_options": second_turn["generation_options"],
            "image_size_confirmed": second_turn["image_size_confirmed"],
            "resume_answers": {"resize_max_pixels": resize_answer},
        }
    )
    generated_call = third_turn["messages"][0].tool_calls[0]  # type: ignore[union-attr]
    assert generated_call["name"] == "generate_image"
    assert generated_call["args"]["seed"] == 42
    assert generated_call["args"]["footnote"] == "Nexus"
    assert generated_call["args"]["resize_max_pixels"] == RESIZE_PIXEL_CHOICES[
        resize_answer
    ]["resize_max_pixels"]


@pytest.mark.asyncio
async def test_validation_resets_size_confirmation_for_a_new_run() -> None:
    """新生图运行不能继承同会话上一轮的尺寸确认状态。"""
    result = await validation_node(
        {
            "run_id": "run-2",
            "validated_run_id": "run-1",
            "intent_validated": True,
            "image_size_confirmed": True,
            "generation_options": {"seed": 42},
            "original_request": "生成另一张商品图",
        }
    )

    assert result["image_size_confirmed"] is False
    assert result["generation_options"] == {}


def test_memory_result_and_attachment_stores_enforce_owner_and_single_binding() -> None:
    """内存适配器遵守与 PostgreSQL 相同的结果读取和附件绑定归属规则。"""
    result_store = MemoryTaskResultStore()
    result_store.save(
        TaskResultRecord(
            task_result_id="123",
            agent=IMAGE_AGENT,
            user_id="user-1",
            conversation_id="456",
            run_id="789",
            message_id=None,
            result_type="image",
            generation_status=TaskResultStatus.SUCCEEDED,
            result_data={
                "outputs": [
                    {
                        "object_key": "memory/generated/user-1/123",
                        "mime_type": "image/png",
                        "file_size": 5,
                    }
                ]
            },
        )
    )
    assert result_store.get_owned("123", "user-2") is None
    assert result_store.get_owned("123", "user-1") is not None

    attachment_store = MemoryAttachmentStore()
    attachment = attachment_store.save("user-1", "reference.png", "image/png", b"png")
    attachment_store.bind_to_message([attachment.attachment_id], "user-1", "conversation-1", "message-1")
    with pytest.raises(AttachmentAccessDeniedError):
        attachment_store.bind_to_message([attachment.attachment_id], "user-1", "conversation-1", "message-2")
