"""定义项目内统一使用的智能体类型字符串枚举。"""

from enum import StrEnum


class AgentType(StrEnum):
    """列出项目已注册的智能体；枚举值同时用于 API 和持久化。"""

    COMMON = "common_agent"
    BASIC_CONVERSATION = "basic_conversation_agent"
    IMAGE = "image_agent"
    LISTING = "listing_agent"
    RESEARCH = "research_agent"
    LABOR_LAW = "labor_law_agent"
    LITERATURE_READER = "literature_reader_agent"
    JOB = "job_agent"
