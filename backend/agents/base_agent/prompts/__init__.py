"""基座默认提示词入口。"""

from agents.base_agent.prompts.loader import load_default_chat_system_prompt

DEFAULT_CHAT_SYSTEM_PROMPT = load_default_chat_system_prompt()

__all__ = ["DEFAULT_CHAT_SYSTEM_PROMPT"]
