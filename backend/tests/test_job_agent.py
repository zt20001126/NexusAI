"""验证求职智能体注册、模型生成岗位及结构化追问路径。"""

import json

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import MemorySaver
from pydantic import ValidationError

from agent.constants import JOB_AGENT
from agents.job_agent import JOB_SYSTEM_PROMPT, create_job_agent
from agents.job_agent.recommendation.schemas import RecommendationRequest
from agents.job_agent.recommendation.service import validate_recommendations
from agents.job_agent.resume_snapshot import JobResumeSnapshot
from agents.job_agent.tools.recommend_job_roles import recommend_job_roles
from agents.registry import PROJECT_AGENT_DEFINITIONS
from tests.fake_models import ScriptedToolCallingModel


def _model_proposal(*, experience_band: str | None = None) -> dict:
    """构造模型自由提出的、生产代码中未预定义的岗位。"""

    profile = {"major": "古典文学", "skills": ["古籍整理"]}
    if experience_band is None:
        profile["experience_years"] = 3
    else:
        profile["experience_band"] = experience_band
    return {
        "profile": profile,
        "roles": [
            {
                "title": "古籍整理专员",
                "reasons": ["古典文学专业与古籍整理经历可用于文献整理工作"],
                "basis_fields": ["major", "skills"],
            }
        ],
    }


async def test_job_agent_supports_registered_multi_turn_chat() -> None:
    """独立图可通过 Checkpointer 持续对话，并作为稳定类型出现在目录中。"""

    definition = next(item for item in PROJECT_AGENT_DEFINITIONS if item.agent == JOB_AGENT)
    assert definition.name == "求职助手"

    assistant = create_job_agent(
        agent=JOB_AGENT,
        chat_model=ScriptedToolCallingModel(),
        checkpointer=MemorySaver(),
    )
    assert "ask_user_questions" in assistant.tool_registry.names
    assert "recommend_job_roles" in assistant.tool_registry.names

    config = {"configurable": {"thread_id": "job-agent-chat-test"}}
    first = await assistant.ainvoke("我想找后端工程师岗位。", runnable_config=config)
    second = await assistant.ainvoke("我有三年开发经验。", runnable_config=config)

    assert first.status == "completed"
    assert second.status == "completed"
    assert first.agent == JOB_AGENT
    assert second.agent == JOB_AGENT


@pytest.mark.parametrize(
    "message",
    [
        "请解读一下我已保存的简历。",
        "请分析一下我已保存简历的不足和改进空间。",
    ],
)
async def test_job_agent_reads_saved_resume_through_no_argument_tool(message: str) -> None:
    """简历解读和不足分析均读取保存内容，再依据工具结果答复。"""

    reader_calls = 0
    snapshot = JobResumeSnapshot(
        status="found",
        intended_position="后端工程师",
        work_experience_years=3,
        skills="Python、PostgreSQL",
    )

    def read_resume() -> JobResumeSnapshot:
        nonlocal reader_calls
        reader_calls += 1
        return snapshot

    assistant = create_job_agent(
        chat_model=_ReadSavedResumeModel(),
        checkpointer=MemorySaver(),
        resume_reader=read_resume,
    )
    resume_tool = next(
        item for item in assistant.tool_registry.tools if item.name == "read_saved_resume"
    )

    assert resume_tool.args_schema is not None
    assert resume_tool.args_schema.model_fields == {}
    response = await assistant.ainvoke(
        message,
        runnable_config={"configurable": {"thread_id": "job-agent-resume-tool-test"}},
    )

    assert response.status == "completed"
    assert response.answer == "已保存资料显示目标岗位为后端工程师。"
    assert reader_calls == 1


def test_job_agent_prompt_defines_scope_and_redirect_behavior() -> None:
    """系统指令说明相关范围、无关话题引导和不调用工具的规则。"""

    assert "求职规划" in JOB_SYSTEM_PROMPT
    assert "求职相关请求按现有能力正常处理" in JOB_SYSTEM_PROMPT
    assert "与求职无关" in JOB_SYSTEM_PROMPT
    assert "说明自己的职责" in JOB_SYSTEM_PROMPT
    assert "引导用户" in JOB_SYSTEM_PROMPT
    assert "不调用 `ask_user_questions` 或 `recommend_job_roles`" in JOB_SYSTEM_PROMPT
    assert "混合请求" in JOB_SYSTEM_PROMPT
    assert "打招呼" in JOB_SYSTEM_PROMPT
    assert "已保存的求职事实" in JOB_SYSTEM_PROMPT
    assert "解读、概括或分析本人已保存简历" in JOB_SYSTEM_PROMPT
    assert "必须在给出结论前调用无参数工具 `read_saved_resume`" in JOB_SYSTEM_PROMPT
    assert "一般简历知识、模板咨询" in JOB_SYSTEM_PROMPT
    assert "简历未写明推断为用户没有相关经历" in JOB_SYSTEM_PROMPT


def test_job_agent_prompt_defines_resume_analysis_result_boundaries() -> None:
    """提示词规定已保存简历不足分析的触发、排除和失败处理边界。"""

    from pathlib import Path

    prompt_path = Path(__file__).parents[1] / "agents" / "job_agent" / "prompts" / "agent.md"
    prompt = prompt_path.read_text(encoding="utf-8")
    assert "本人简历不足分析" in prompt
    assert "解读、概括、分析本人已保存简历" in prompt
    assert "根据本人简历推荐" in prompt
    assert "一般岗位推荐不自动视为简历分析" in prompt
    assert "一般简历知识、模板咨询" in prompt
    assert "`found`" in prompt and "`not_found`" in prompt and "`unavailable`" in prompt
    assert "不得把字段为空或未返回写成用户没有相应经历" in prompt


def test_job_agent_system_prompt_requires_resume_for_resume_based_requests() -> None:
    """系统提示明确简历解读和基于简历推荐的读取触发规则。"""

    assert "解读、概括或分析本人已保存简历" in JOB_SYSTEM_PROMPT
    assert "根据本人简历推荐岗位" in JOB_SYSTEM_PROMPT
    assert "一般岗位咨询" in JOB_SYSTEM_PROMPT


class _ReadSavedResumeModel:
    """先调用简历工具，再根据工具观察组织自然语言回复。"""

    def bind_tools(self, tools: list[object]) -> "_ReadSavedResumeModel":
        self.tool_names = {getattr(item, "name") for item in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        latest = messages[-1]
        if isinstance(latest, ToolMessage):
            assert latest.name == "read_saved_resume"
            result = json.loads(str(latest.content))
            position = result["data"]["intended_position"]
            return AIMessage(content=f"已保存资料显示目标岗位为{position}。")

        assert "read_saved_resume" in self.tool_names
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_saved_resume",
                    "args": {},
                    "id": "read-saved-resume-call",
                    "type": "tool_call",
                }
            ],
        )


class _ResumeBasedRecommendationModel:
    """模拟读取保存简历、用其字段提交岗位建议并使用校验结果回复。"""

    def __init__(self) -> None:
        self.tool_results: list[str] = []

    def bind_tools(self, tools: list[object]) -> "_ResumeBasedRecommendationModel":
        self.tool_names = {getattr(tool, "name") for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        latest = messages[-1]
        if isinstance(latest, ToolMessage):
            self.tool_results.append(latest.name)
            result = json.loads(str(latest.content))
            if latest.name == "read_saved_resume":
                snapshot = result["data"]
                if snapshot["status"] != "found":
                    return AIMessage(content="目前没有可读取的已保存简历，请提供简历内容。")
                return AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "recommend_job_roles",
                            "args": {
                                "profile": {
                                    "experience_years": snapshot["work_experience_years"],
                                    "skills": snapshot["skills"].split("、"),
                                },
                                "roles": [
                                    {
                                        "title": "后端工程师",
                                        "reasons": ["简历列出的 Python 和 PostgreSQL 与岗位方向相关"],
                                        "basis_fields": ["skills", "experience_years"],
                                    }
                                ],
                            },
                            "id": "recommend-from-resume",
                            "type": "tool_call",
                        }
                    ],
                )
            return AIMessage(content=f"推荐方向：{result['data']['roles'][0]['title']}")

        assert {"read_saved_resume", "recommend_job_roles"} <= self.tool_names
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "read_saved_resume",
                    "args": {},
                    "id": "read-before-recommendation",
                    "type": "tool_call",
                }
            ],
        )


class _DirectResponseModel:
    """模拟一般岗位咨询直接使用当前对话而不读取简历。"""

    def bind_tools(self, tools: list[object]) -> "_DirectResponseModel":
        self.tool_names = {getattr(tool, "name") for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        del messages
        return AIMessage(content="请告诉我你的专业、技能和相关经验，我会据此推荐岗位方向。")


async def test_resume_based_job_recommendation_reads_resume_before_validation() -> None:
    """明确要求依据简历推荐时，先读取简历再调用岗位建议校验工具。"""

    model = _ResumeBasedRecommendationModel()
    assistant = create_job_agent(
        chat_model=model,
        checkpointer=MemorySaver(),
        resume_reader=lambda: JobResumeSnapshot(
            status="found",
            work_experience_years=3,
            skills="Python、PostgreSQL",
        ),
    )

    response = await assistant.ainvoke(
        "根据我已保存的简历推荐适合的工作岗位。",
        runnable_config={"configurable": {"thread_id": "resume-based-role-test"}},
    )

    assert response.status == "completed"
    assert response.answer == "推荐方向：后端工程师"
    assert model.tool_results == ["read_saved_resume", "recommend_job_roles"]


@pytest.mark.parametrize("resume_status", ["not_found", "unavailable"])
async def test_resume_recommendation_without_saved_resume_does_not_invent_facts(
    resume_status: str,
) -> None:
    """没有可读简历时不提交岗位建议工具，也不伪造简历结论。"""

    model = _ResumeBasedRecommendationModel()
    assistant = create_job_agent(
        chat_model=model,
        checkpointer=MemorySaver(),
        resume_reader=lambda: JobResumeSnapshot(status=resume_status),
    )

    response = await assistant.ainvoke(
        "根据我的简历推荐适合的工作岗位。",
        runnable_config={"configurable": {"thread_id": f"resume-{resume_status}-test"}},
    )

    assert response.status == "completed"
    assert "没有可读取的已保存简历" in response.answer
    assert model.tool_results == ["read_saved_resume"]


async def test_general_job_question_does_not_require_saved_resume() -> None:
    """一般岗位咨询继续使用当前对话资料，不要求读取保存简历。"""

    reader_calls = 0

    def read_resume() -> JobResumeSnapshot:
        nonlocal reader_calls
        reader_calls += 1
        return JobResumeSnapshot(status="found")

    assistant = create_job_agent(
        chat_model=_DirectResponseModel(),
        checkpointer=MemorySaver(),
        resume_reader=read_resume,
    )

    response = await assistant.ainvoke(
        "我适合什么岗位？",
        runnable_config={"configurable": {"thread_id": "general-role-question-test"}},
    )

    assert response.status == "completed"
    assert reader_calls == 0


class _OffTopicResponseModel:
    """模拟模型收到无关话题后直接给出职责说明，不调用工具。"""

    def bind_tools(self, tools: list[object]) -> "_OffTopicResponseModel":
        self.tool_names = {getattr(tool, "name") for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        return AIMessage(
            content=(
                "我是求职助手，可以帮你规划求职方向、推荐岗位、梳理经历和准备面试。"
                "你可以告诉我专业、技能、工作经验或想找的岗位。"
            )
        )


async def test_off_topic_message_gets_scope_guidance_without_question_card() -> None:
    """无关消息以普通回复完成，不进入题卡等待流程。"""

    assistant = create_job_agent(
        chat_model=_OffTopicResponseModel(),
        checkpointer=MemorySaver(),
    )
    response = await assistant.ainvoke(
        "明天会下雨吗？",
        runnable_config={"configurable": {"thread_id": "job-agent-off-topic-test"}},
    )

    assert response.status == "completed"
    assert response.questions is None
    assert "求职助手" in response.answer
    assert "专业、技能、工作经验" in response.answer


def test_model_can_propose_role_without_predefined_catalog() -> None:
    """模型提供任意岗位名称和依据后，工具原样返回通过校验的建议。"""

    proposal = _model_proposal()
    raw = recommend_job_roles.invoke(proposal)
    payload = json.loads(raw)

    assert payload["success"] is True
    assert payload["data"]["status"] == "completed"
    assert payload["data"]["roles"][0]["title"] == "古籍整理专员"


def test_missing_facts_block_premature_recommendation() -> None:
    """缺少经验时即使模型提出岗位，也先返回待补充资料。"""

    proposal = _model_proposal()
    del proposal["profile"]["experience_years"]
    result = validate_recommendations(RecommendationRequest.model_validate(proposal))

    assert result.status == "needs_more_information"
    assert result.roles == []
    assert "相关工作经验年限或区间" in result.missing_information


def test_recommendation_requires_actual_basis_and_disallows_age_basis() -> None:
    """年龄不能成为依据，引用未提供的专业等资料也不能通过工具。"""

    proposal = _model_proposal()
    proposal["profile"]["age"] = 25
    proposal["roles"][0]["basis_fields"] = ["age"]
    with pytest.raises(ValidationError):
        RecommendationRequest.model_validate(proposal)

    proposal["roles"][0]["basis_fields"] = ["education"]
    result = validate_recommendations(RecommendationRequest.model_validate(proposal))
    assert result.status == "no_recommendation"
    assert result.roles == []


def test_model_may_abstain_without_catalog_fallback() -> None:
    """模型无法可靠推荐时返回空建议，不用预设目录填充。"""

    proposal = _model_proposal()
    proposal["roles"] = []
    result = validate_recommendations(RecommendationRequest.model_validate(proposal))
    assert result.status == "no_recommendation"
    assert result.roles == []


class _ScriptedJobRecommendationModel:
    """离线模拟追问、恢复、模型生成建议、工具校验和最终回答。"""

    def bind_tools(self, tools: list[object]) -> "_ScriptedJobRecommendationModel":
        self.tool_names = {getattr(tool, "name") for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        latest = messages[-1]
        if isinstance(latest, ToolMessage) and latest.name == "recommend_job_roles":
            result = json.loads(str(latest.content))["data"]
            return AIMessage(content=f"推荐方向：{result['roles'][0]['title']}")
        if isinstance(latest, HumanMessage) and "1年以内" in str(latest.content):
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "recommend_job_roles",
                        "args": _model_proposal(experience_band="junior"),
                        "id": "recommend-after-answer",
                        "type": "tool_call",
                    }
                ],
            )
        assert {"ask_user_questions", "recommend_job_roles"} <= self.tool_names
        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ask_user_questions",
                    "args": {
                        "questions": [
                            {
                                "id": "experience_band",
                                "title": "你的相关工作经验属于哪个范围？",
                                "type": "SingleChoice",
                                "options": [
                                    {"label": "暂无", "description": "没有相关工作经验"},
                                    {"label": "1年以内", "description": "少于一年相关工作经验"},
                                    {"label": "1-3年", "description": "一至三年相关工作经验"},
                                    {"label": "3年以上", "description": "三年以上相关工作经验"},
                                ],
                                "allow_custom_input": False,
                            }
                        ]
                    },
                    "id": "ask-experience",
                    "type": "tool_call",
                }
            ],
        )


async def test_job_agent_asks_then_uses_model_proposal() -> None:
    """同一会话先等待经验答案，再校验模型提出的岗位并完成回复。"""

    assistant = create_job_agent(
        chat_model=_ScriptedJobRecommendationModel(),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "job-recommendation-test"}}

    waiting = await assistant.ainvoke("我学古典文学，会古籍整理，适合什么岗位？", runnable_config=config)
    assert waiting.status == "waiting"
    assert waiting.questions is not None
    assert waiting.questions.questions[0].id == "experience_band"

    completed = await assistant.ainvoke(
        '{"experience_band":"1年以内"}', runnable_config=config
    )
    assert completed.status == "completed"
    assert completed.answer == "推荐方向：古籍整理专员"
