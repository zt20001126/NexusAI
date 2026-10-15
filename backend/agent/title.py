"""生成并规范化新会话标题，隔离模型调用与智能体运行流程。"""

import asyncio
import logging
from typing import Any, Protocol

from langchain_core.messages import HumanMessage, SystemMessage

from agent.prompts.conversation_title import CONVERSATION_TITLE_SYSTEM_PROMPT
from infra.model_provider import ChatModelProvider

logger = logging.getLogger(__name__)

MAX_CONVERSATION_TITLE_LENGTH = 15
MAX_CONVERSATION_TITLE_SOURCE_LENGTH = 4_000
FALLBACK_CONVERSATION_TITLE = "新会话"


class ConversationTitleGenerator(Protocol):
    """会话标题生成边界，供运行器调用并由测试替换。"""

    async def generate_title(self, first_user_message: str) -> str | None: ...


class ModelConversationTitleGenerator:
    """通过项目统一模型 Provider 根据首条用户消息生成标题。"""

    def __init__(self, model_provider: ChatModelProvider, timeout_seconds: int) -> None:
        """注入模型 Provider 和标题调用时限。"""
        self._model_provider = model_provider
        self._timeout_seconds = timeout_seconds

    async def generate_title(self, first_user_message: str) -> str | None:
        """调用模型并验证标题；失败时返回空值，由运行器采用安全回退标题。"""
        source = first_user_message.strip()
        if not source:
            return None

        messages = [
            SystemMessage(content=CONVERSATION_TITLE_SYSTEM_PROMPT),
            HumanMessage(content=source[:MAX_CONVERSATION_TITLE_SOURCE_LENGTH]),
        ]
        try:
            model = self._model_provider.create_chat_model()
            async with asyncio.timeout(self._timeout_seconds):
                response = await model.ainvoke(messages)
        except TimeoutError:
            logger.warning("会话标题模型调用超时")
            return None
        except Exception:
            logger.exception("会话标题模型调用失败")
            return None

        return normalize_conversation_title(getattr(response, "content", response))


def normalize_conversation_title(content: Any) -> str | None:
    """清理模型输出，只保留首行标题并限制最大长度。"""
    if isinstance(content, str):
        text = content
    elif isinstance(content, list):
        text_parts = [
            item
            if isinstance(item, str)
            else item["text"]
            for item in content
            if isinstance(item, str)
            or (isinstance(item, dict) and isinstance(item.get("text"), str))
        ]
        text = "".join(text_parts)
    else:
        return None

    first_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    title = " ".join(first_line.split()).strip(" \t\r\n\"'“”‘’`#")
    for prefix in ("标题：", "标题:"):
        if title.startswith(prefix):
            title = title[len(prefix):].strip()
            break
    title = title.strip(" \t\r\n\"'“”‘’`#")
    title = title[:MAX_CONVERSATION_TITLE_LENGTH].strip()
    return title or None


def fallback_conversation_title(first_user_message: str) -> str:
    """模型不可用时从首条消息生成兼容现有行为的回退标题。"""
    title = " ".join(first_user_message.split())[:MAX_CONVERSATION_TITLE_LENGTH]
    return title or FALLBACK_CONVERSATION_TITLE
