"""共享结构化追问的题数边界测试。"""

import pytest

from agent.schemas.question import Question, QuestionPayload
from app.schemas.agent import ResumeRequest


def _question(question_id: str, title: str) -> Question:
    """构造符合当前协议的四选项题卡。"""
    return Question(
        id=question_id,
        title=title,
        type="SingleChoice",
        allow_custom_input=False,
        options=[
            {"label": "选项一", "description": "说明一"},
            {"label": "选项二", "description": "说明二"},
            {"label": "选项三", "description": "说明三"},
            {"label": "选项四", "description": "说明四"},
        ],
    )


def test_question_payload_and_resume_request_allow_at_most_three_questions() -> None:
    """公共问题载荷和恢复请求都遵守每轮三题上限。"""
    questions = [
        _question(f"question_{index}", f"请回答问题 {index}。")
        for index in range(1, 4)
    ]
    QuestionPayload(questions=questions)

    with pytest.raises(ValueError):
        QuestionPayload(
            questions=[
                *questions,
                _question("question_4", "请回答问题 4。"),
            ]
        )

    ResumeRequest(
        conversation_id="1",
        answers={f"question_{index}": "答案" for index in range(1, 4)},
        request_id="question-resume-id-0001",
    )
    with pytest.raises(ValueError):
        ResumeRequest(
            conversation_id="1",
            answers={f"question_{index}": "答案" for index in range(1, 5)},
        )


def test_question_payload_validates_structured_options_by_label() -> None:
    """结构化选项的答案仍以 label 字符串提交和校验。"""
    payload = QuestionPayload.model_validate(
        {
            "questions": [
                {
                    "id": "platform",
                    "title": "你想在哪个平台选品？",
                    "type": "SingleChoice",
                    "allow_custom_input": False,
                    "options": [
                        {"label": "Amazon", "description": "面向亚马逊市场"},
                        {"label": "TikTok Shop", "description": "面向 TikTok Shop 市场"},
                        {"label": "独立站", "description": "面向独立站市场"},
                        {"label": "其他平台", "description": "面向其他销售平台"},
                    ],
                }
            ]
        }
    )

    payload.validate_answers({"platform": "Amazon"})
    with pytest.raises(ValueError):
        payload.validate_answers({"platform": "Not listed"})
