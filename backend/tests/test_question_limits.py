"""共享结构化追问的题数边界测试。"""

import pytest

from agent.schemas.question import Question, QuestionPayload
from app.schemas.agent import ResumeRequest


def test_question_payload_and_resume_request_allow_at_most_three_questions() -> None:
    """公共问题载荷和恢复请求都遵守每轮三题上限。"""
    questions = [
        Question(id=f"question_{index}", title=f"问题 {index}", prompt=f"请回答问题 {index}。")
        for index in range(1, 4)
    ]
    QuestionPayload(questions=questions)

    with pytest.raises(ValueError):
        QuestionPayload(
            questions=[
                *questions,
                Question(
                    id="question_4",
                    title="问题 4",
                    prompt="请回答问题 4。",
                ),
            ]
        )

    ResumeRequest(
        conversation_id="1",
        answers={f"question_{index}": "答案" for index in range(1, 4)},
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
                    "options": [
                        {"label": "Amazon", "description": "面向亚马逊市场"},
                        {"label": "TikTok Shop", "description": "面向 TikTok Shop 市场"},
                    ],
                }
            ]
        }
    )

    payload.validate_answers({"platform": "Amazon"})
    with pytest.raises(ValueError):
        payload.validate_answers({"platform": "Not listed"})
