"""listing生成智能体的模型、Schema 和追问测试。"""

import base64
import json

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from agent.persistence.memory import MemoryAttachmentStore, MemoryTaskResultStore
from agents.listing_agent.nodes import create_plan_node, create_vision_node
from agents.listing_agent.schemas import (
    ListingImageAnalysis,
    ListingPlan,
    ListingResult,
)
from agents.listing_agent.tools.task_result import create_listing_task_result_tools


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


def test_ask_listing_questions_persists_json_compatible_image_analysis() -> None:
    """追问工具将嵌套 Pydantic 图片分析对象转换为可持久化 JSON。"""
    task_result_store = MemoryTaskResultStore()
    ask_tool, _ = create_listing_task_result_tools(task_result_store)
    image_analysis = {
        "candidate_category": "水杯",
        "visible_features": ["蓝色杯身"],
        "packaging_text": [],
        "visible_claims": [],
        "uncertain_observations": [],
    }

    ask_tool.invoke(
        {
            "questions": [
                {
                    "id": "brand",
                    "title": "品牌",
                    "prompt": "请确认商品品牌。",
                    "allow_custom_input": True,
                }
            ],
            "task_result_id": "task-result-1",
            "principal_id": "seller-1",
            "conversation_id": "conversation-1",
            "run_id": "run-1",
            "original_request": "生成商品 Listing",
            "attachment_ids": ["attachment-1"],
            "image_analysis": image_analysis,
            "product_facts": {"类别": "水杯"},
            "confirmed_answers": {},
        }
    )

    record = task_result_store.records["task-result-1"]
    assert record.input_data["image_analysis"] == image_analysis
    assert json.loads(json.dumps(record.input_data)) == record.input_data


@pytest.mark.asyncio
async def test_deepseek_vision_sends_images_and_parses_ocr_observations() -> None:
    """视觉节点向 DeepSeek ChatModel 发送 Base64 图片并校验结构化观察。"""
    analysis = ListingImageAnalysis(
        candidate_category="咖啡杯",
        visible_features=["白色杯身"],
        packaging_text=["容量 350ml"],
        visible_claims=[],
        uncertain_observations=["材质无法从图片确认"],
    )

    class _RecordingChatModel:
        def __init__(self) -> None:
            self.messages: list[BaseMessage] = []

        async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
            self.messages = messages
            return AIMessage(content=analysis.model_dump_json())

    attachment_store = MemoryAttachmentStore()
    attachment = attachment_store.save("seller", "cup.png", "image/png", b"picture-bytes")
    attachment_store.bind_to_message(
        [attachment.attachment_id], "seller", "conversation", "message"
    )
    chat_model = _RecordingChatModel()
    node = create_vision_node(chat_model, attachment_store)

    result = await node(
        {
            "attachment_ids": [attachment.attachment_id],
            "principal_id": "seller",
            "conversation_id": "conversation",
        }
    )

    assert isinstance(chat_model.messages[0], SystemMessage)
    assert isinstance(chat_model.messages[1], HumanMessage)
    user_content = chat_model.messages[1].content
    assert isinstance(user_content, list)
    image_url = user_content[1]["image_url"]["url"]
    assert image_url == f"data:image/png;base64,{base64.b64encode(b'picture-bytes').decode()}"
    assert result["image_analysis"]["packaging_text"] == ["容量 350ml"]


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
