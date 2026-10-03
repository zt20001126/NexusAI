"""无需网络的工具调用模型，供运行时和 API 测试注入。"""

import json
import uuid
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, ToolMessage


class ScriptedToolCallingModel:
    """首轮追问目标，恢复后将目标交给示例整理工具。"""

    def bind_tools(
        self,
        tools: list[Any],
        **_: Any,
    ) -> "ScriptedToolCallingModel":
        self._tool_names = {tool.name for tool in tools}
        return self

    async def ainvoke(self, messages: list[BaseMessage]) -> AIMessage:
        has_question = any(
            isinstance(message, ToolMessage) and message.name == "ask_user_question"
            for message in messages
        )
        if has_question and "summarize_goal" in self._tool_names:
            content = str(messages[-1].content)
            try:
                decoded = json.loads(content)
            except json.JSONDecodeError:
                decoded = {}
            goal = decoded.get("goal", content) if isinstance(decoded, dict) else content
            tool_name = "summarize_goal"
            arguments = {"goal": str(goal)}
        else:
            tool_name = "ask_user_question"
            arguments = {}
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
