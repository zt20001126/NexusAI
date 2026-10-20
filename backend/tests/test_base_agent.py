"""基础智能体题卡工具的结构边界测试。"""

import pytest
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from agent.constants import BASE_CONVERSATION_AGENT
from agents.base_agent import (
    BaseAgent,
    BaseAgentConfig,
    create_basic_conversation_agent,
)
from agents.base_agent.tools.ask_user_questions import BaseAgentQuestionPayload
from tests.fake_models import ScriptedQuestionCallingModel


def _question(**overrides: object) -> dict[str, object]:
    """构造一个符合基础智能体单选题协议的示例题目。"""

    question: dict[str, object] = {
        "id": "plan_style",
        "title": "你希望计划采用哪种推进方式？",
        "type": "SingleChoice",
        "options": [
            {"label": "稳步推进", "description": "按较小任务逐步完成"},
            {"label": "集中冲刺", "description": "在短时间内投入较多精力"},
            {"label": "弹性安排", "description": "根据每周情况调整节奏"},
            {"label": "轻量尝试", "description": "先用较少投入验证方向"},
        ],
        "allow_custom_input": False,
    }
    question.update(overrides)
    return question


def test_question_payload_accepts_one_to_three_single_choice_questions() -> None:
    """基础工具接受 1–3 道共享结构的单选题。"""

    payload = BaseAgentQuestionPayload.model_validate(
        {"questions": [_question(), _question(id="time_budget"), _question(id="goal")]}
    )

    assert len(payload.questions) == 3
    assert all(question.type == "SingleChoice" for question in payload.questions)


@pytest.mark.parametrize(
    "questions",
    [
        [],
        [_question() for _ in range(4)],
        [_question(type="MultiChoice")],
        [_question(options=[{"label": "只有一项", "description": "不符合四选项协议"}])],
        [
            _question(
                options=[
                    {"label": "相同", "description": "选项一"},
                    {"label": "相同", "description": "选项二"},
                    {"label": "选项三", "description": "说明三"},
                    {"label": "选项四", "description": "说明四"},
                ]
            )
        ],
        [_question(), _question()],
        [_question(allow_custom_input=True)],
    ],
)
def test_question_payload_rejects_out_of_contract_questions(
    questions: list[dict[str, object]],
) -> None:
    """基础工具拒绝空批次、超量、多选及非四选项题目。"""

    with pytest.raises(ValidationError):
        BaseAgentQuestionPayload.model_validate({"questions": questions})


async def test_basic_agent_returns_waiting_question_then_resumes_answering() -> None:
    """基础助手直接调用时返回题卡状态，并在同一 Checkpoint 会话继续回答。"""

    assistant = create_basic_conversation_agent(
        agent=BASE_CONVERSATION_AGENT,
        chat_model=ScriptedQuestionCallingModel(),
        checkpointer=MemorySaver(),
    )
    assert "ask_user_questions" in assistant.tool_registry.names
    runnable_config = {
        "configurable": {"thread_id": "base-agent-question-test"},
    }

    question_response = await assistant.ainvoke(
        "请用题卡让我选择计划风格。",
        runnable_config=runnable_config,
    )

    assert question_response.status == "waiting"
    assert question_response.answer is None
    assert question_response.questions is not None
    assert question_response.questions.questions[0].type == "SingleChoice"

    answer_response = await assistant.ainvoke(
        "我选稳步推进。",
        runnable_config=runnable_config,
    )

    assert answer_response.status == "completed"
    assert answer_response.questions is None
    assert answer_response.answer == "我会按“稳步推进”的风格安排计划。"


def test_custom_base_agent_does_not_receive_question_tool_implicitly() -> None:
    """低层基座只注册调用方显式传入的工具。"""

    assistant = BaseAgent(
        config=BaseAgentConfig(
            agent=BASE_CONVERSATION_AGENT,
            system_prompt="直接回答用户。",
        ),
        chat_model=ScriptedQuestionCallingModel(),
        checkpointer=MemorySaver(),
    )

    assert "ask_user_questions" not in assistant.tool_registry.names
