"""加载并组合基础对话助手的系统提示词和 Agent 行为指令。"""

from pathlib import Path


_PROMPTS_DIRECTORY = Path(__file__).parent


def load_default_chat_system_prompt() -> str:
    """从 Markdown 文件读取提示词段落并按固定顺序组合。"""

    system_prompt = (
        (_PROMPTS_DIRECTORY / "system.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    agent_instructions = (
        (_PROMPTS_DIRECTORY / "agent.md")
        .read_text(encoding="utf-8")
        .strip()
    )
    return f"{system_prompt}\n\n{agent_instructions}\n"
