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
