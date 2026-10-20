"""无需网络的工具调用模型，供运行时和 API 测试注入。"""

import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class ScriptedToolCallingModel:
    """通用对话先自然澄清；收到目标信息后调用示例整理工具。"""

    def bind_tools(
        self,
        tools: list[Any],
        **_: Any,
    ) -> "ScriptedToolCallingModel":
        self._tool_names = {tool.name for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        has_summary = any(
            isinstance(message, ToolMessage) and message.name == "summarize_goal"
            for message in messages
        )
        if has_summary and "summarize_goal" in self._tool_names:
            content = str(messages[-1].content)
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                decoded = {}
            goal = decoded.get("goal", content) if isinstance(decoded, dict) else content
            tool_name = "summarize_goal"
            arguments = {"goal": str(goal)}
        else:
            return AIMessage(content="你希望整理哪类开发目标？")
        return AIMessage(
            content="",
            tool_calls=[{
                "name": tool_name,
                "args": arguments,
                "id": f"test-tool-{uuid.uuid4().hex}",
                "type": "tool_call",
            }],
        )


class ScriptedToolCallingProvider:
    """创建不会访问网络的工具调用模型。"""

    def create_chat_model(self) -> ScriptedToolCallingModel:
        return ScriptedToolCallingModel()


class ScriptedQuestionCallingModel:
    """首轮提出单选题卡，收到答案后返回包含所选项的完成回复。"""

    def bind_tools(
        self,
        tools: list[Any],
        **_: Any,
    ) -> "ScriptedQuestionCallingModel":
        self._tool_names = {tool.name for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        """按题卡工具是否已获答复确定性地产生工具调用或最终回复。"""

        if "ask_user_questions" not in self._tool_names:
            return AIMessage(content="当前没有题卡工具。")

        has_question_result = any(
            isinstance(message, ToolMessage)
            and message.name == "ask_user_questions"
            for message in messages
        )
        if has_question_result:
            latest_user_message = next(
                (
                    message.content
                    for message in reversed(messages)
                    if message.type == "human"
                ),
                "",
            )
            try:
                decoded_answer = json.loads(str(latest_user_message))
            except json.JSONDecodeError:
                decoded_answer = latest_user_message
            if isinstance(decoded_answer, dict):
                selected_style = decoded_answer.get("plan_style", "未提供")
            else:
                selected_style = next(
                    (
                        option
                        for option in ("稳步推进", "集中冲刺", "弹性安排", "轻量尝试")
                        if option in str(decoded_answer)
                    ),
                    str(decoded_answer),
                )
            return AIMessage(content=f"我会按“{selected_style}”的风格安排计划。")

        return AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "ask_user_questions",
                    "args": {
                        "questions": [
                            {
                                "id": "plan_style",
                                "title": "你希望计划采用哪种推进方式？",
                                "type": "SingleChoice",
                                "options": [
                                    {
                                        "label": "稳步推进",
                                        "description": "按较小任务逐步完成",
                                    },
                                    {
                                        "label": "集中冲刺",
                                        "description": "在短时间内投入较多精力",
                                    },
                                    {
                                        "label": "弹性安排",
                                        "description": "根据每周情况调整节奏",
                                    },
                                    {
                                        "label": "轻量尝试",
                                        "description": "先用较少投入验证方向",
                                    },
                                ],
                                "allow_custom_input": False,
                            }
                        ]
                    },
                    "id": "scripted-question-call",
                    "type": "tool_call",
                }
            ],
        )


class ScriptedQuestionCallingProvider:
    """创建确定性题卡模型，供基座和 Runner 集成测试使用。"""

    def create_chat_model(self) -> ScriptedQuestionCallingModel:
        return ScriptedQuestionCallingModel()
