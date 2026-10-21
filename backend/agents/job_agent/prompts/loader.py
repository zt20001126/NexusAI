"""加载并组合求职智能体的系统提示词和行为指令。"""

from pathlib import Path


_PROMPTS_DIRECTORY = Path(__file__).parent


def load_job_system_prompt() -> str:
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
