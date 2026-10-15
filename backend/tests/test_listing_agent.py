"""淘宝 Listing 生成智能体的模型、Schema 和追问测试。"""

import base64
import json

import httpx
import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from agents.listing_agent.nodes import create_plan_node
from agents.listing_agent.providers.tokenhub_vision import (
    TokenHubVisionClient,
    TokenHubVisionError,
)
from agents.listing_agent.schemas import ListingImageAnalysis, ListingPlan, ListingResult
from infra.settings import AppSettings


def _listing_result(description: str = "适合日常使用的便携水杯。") -> dict[str, object]:
    """生成可用于 Schema 边界测试的合法 Listing JSON。"""
    return {
        "schema_version": "1.0",
        "product_facts": {"类别": "水杯"},
        "image_analysis": {
            "candidate_category": "水杯",
            "visible_features": ["蓝色杯身"],
            "packaging_text": [],
            "visible_claims": [],
            "uncertain_observations": [],
        },
        "versions": [
            {
                "version": version,
                "title": f"便携水杯 蓝色款 {version}",
                "selling_points": ["便携设计", "蓝色外观", "日常使用"],
                "description": description,
                "keywords": ["便携水杯", "蓝色水杯", "日常水杯"],
                "product_attributes": {"颜色": "蓝色"},
            }
            for version in (1, 2, 3)
        ],
    }


def test_listing_result_requires_three_versions_and_plain_text_description() -> None:
    """输出校验固定三版，并拒绝富文本详情描述。"""
    parsed = ListingResult.model_validate(_listing_result())
    assert [item.version for item in parsed.versions] == [1, 2, 3]

    two_versions = _listing_result()
    two_versions["versions"] = two_versions["versions"][:2]  # type: ignore[index]
    with pytest.raises(ValueError):
        ListingResult.model_validate(two_versions)

    with pytest.raises(ValueError):
        ListingResult.model_validate(_listing_result("**重点** 内容"))


def test_listing_plan_rejects_unstable_ids_and_unsupported_question_types() -> None:
    """规划输出只接受稳定 ID 和前端可完整回答的题型。"""
    with pytest.raises(ValueError):
        ListingPlan.model_validate(
            {
                "questions": [
                    {
                        "id": "brand-name",
                        "title": "品牌",
                        "prompt": "请确认品牌。",
                        "type": "TextQuestion",
                    }
                ]
            }
        )

    with pytest.raises(ValueError):
        ListingPlan.model_validate(
            {
                "questions": [
                    {
                        "id": "brand",
                        "title": "品牌",
                        "prompt": "请上传品牌授权资料。",
                        "type": "FileUpload",
                    }
                ]
            }
        )


@pytest.mark.asyncio
async def test_tokenhub_vision_sends_images_and_parses_ocr_observations() -> None:
    """视觉请求把图片作为 Base64 image_url 发送并校验结构化观察。"""
    captured: dict[str, object] = {}
    analysis = ListingImageAnalysis(
        candidate_category="咖啡杯",
        visible_features=["白色杯身"],
        packaging_text=["容量 350ml"],
        visible_claims=[],
        uncertain_observations=["材质无法从图片确认"],
    )

    def respond(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": analysis.model_dump_json()}}]},
        )

    client = TokenHubVisionClient(
        AppSettings(tokenhub_api_key="test-secret", _env_file=None),
        transport=httpx.MockTransport(respond),
    )
    result = await client.analyze([("image/png", b"picture-bytes")])

    request_body = captured["body"]
    assert captured["authorization"] == "Bearer test-secret"
    assert request_body["model"] == "hy-vision-2.0-instruct"
    image_url = request_body["messages"][0]["content"][1]["image_url"]["url"]
    assert image_url == f"data:image/png;base64,{base64.b64encode(b'picture-bytes').decode()}"
    assert result.packaging_text == ["容量 350ml"]


@pytest.mark.asyncio
async def test_tokenhub_vision_maps_provider_errors_without_leaking_body() -> None:
    """视觉 Provider 将上游错误转换为稳定提示，避免泄漏响应正文。"""
    client = TokenHubVisionClient(
        AppSettings(tokenhub_api_key="test-secret", _env_file=None),
        transport=httpx.MockTransport(
            lambda request: httpx.Response(401, text="private-upstream-detail")
        ),
    )

    with pytest.raises(TokenHubVisionError) as raised:
        await client.analyze([("image/jpeg", b"picture")])

    assert raised.value.code == "TOKENHUB_AUTH_FAILED"
    assert "private-upstream-detail" not in raised.value.public_message


@pytest.mark.asyncio
async def test_plan_merges_answer_and_does_not_repeat_its_question_id() -> None:
    """必要问题按稳定 ID 批量返回，已回答问题不会重复追问。"""
    model = FakeListChatModel(
        responses=[
            json.dumps(
                {
                    "product_facts": {"类别": "水杯"},
                    "questions": [
                        {
                            "id": "capacity",
                            "title": "容量",
                            "prompt": "请确认实际容量。",
                            "type": "TextQuestion",
                            "allow_custom_input": True,
                        },
                        {
                            "id": "material",
                            "title": "材质",
                            "prompt": "请确认商品材质。",
                            "type": "TextQuestion",
                            "allow_custom_input": True,
                        },
                    ],
                },
                ensure_ascii=False,
            )
        ]
    )
    node = create_plan_node(model)

    result = await node(
        {
            "original_request": "蓝色水杯",
            "image_analysis": {"candidate_category": "水杯"},
            "resume_answers": {"capacity": "500 毫升"},
            "confirmed_answers": {},
        }
    )

    assert result["confirmed_answers"] == {"capacity": "500 毫升"}
    assert [item["id"] for item in result["questions"]] == ["material"]
