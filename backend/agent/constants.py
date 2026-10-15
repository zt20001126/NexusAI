"""共享智能体标识与输入边界常量。"""

# 注册表、持久化和前端 API 共用的稳定智能体标识。
COMMON_AGENT_ID = "common_agent"
IMAGE_AGENT_ID = "image_agent"
LISTING_AGENT_ID = "listing_agent"
RESEARCH_AGENT_ID = "research_agent"
LABOR_LAW_AGENT_ID = "labor_law_agent"

# Checkpoint 线程 ID 已落库，保留旧代码片段以便继续读取已有会话状态。
CHECKPOINT_AGENT_NAMESPACE_COMPATIBILITY: dict[str, str] = {
    COMMON_AGENT_ID: "default",
    IMAGE_AGENT_ID: "taobao_image",
}

# 单次生图允许附带的参考图片数量。
MAX_REFERENCE_IMAGE_COUNT = 3
# 每张参考图片的最大字节数，按 5 MiB 计算。
MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024
# 进入 TokenHub 请求前允许的参考图片总字节数。
MAX_REFERENCE_IMAGE_TOTAL_BYTES = MAX_REFERENCE_IMAGE_COUNT * MAX_REFERENCE_IMAGE_BYTES
# 单批结构化追问的题目数量上限，所有智能体共享此边界。
MAX_QUESTIONS_PER_BATCH = 5
# 同一次智能体运行最多向用户发出的问题批次数。
MAX_QUESTION_ROUNDS_PER_RUN = 3
# 单个单选题或多选题允许配置的选项数；与历史接口边界保持兼容。
MAX_QUESTION_OPTIONS = 100
# 单个选项的最大字符数。
MAX_QUESTION_OPTION_CHARS = 100
# 单个多选题允许提交的最大选中项数；与既有恢复接口限制保持一致。
MAX_QUESTION_SELECTION_COUNT = 20
# 单个文本答案的最大字符数。
MAX_QUESTION_ANSWER_CHARS = 2_000
# 多选题单个自定义选项的最大字符数。
MAX_QUESTION_SELECTION_CHARS = 500

__all__ = [
    "COMMON_AGENT_ID",
    "IMAGE_AGENT_ID",
    "CHECKPOINT_AGENT_NAMESPACE_COMPATIBILITY",
    "LISTING_AGENT_ID",
    "RESEARCH_AGENT_ID",
    "LABOR_LAW_AGENT_ID",
    "MAX_REFERENCE_IMAGE_BYTES",
    "MAX_REFERENCE_IMAGE_COUNT",
    "MAX_REFERENCE_IMAGE_TOTAL_BYTES",
    "MAX_QUESTIONS_PER_BATCH",
    "MAX_QUESTION_ROUNDS_PER_RUN",
    "MAX_QUESTION_OPTIONS",
    "MAX_QUESTION_OPTION_CHARS",
    "MAX_QUESTION_SELECTION_COUNT",
    "MAX_QUESTION_ANSWER_CHARS",
    "MAX_QUESTION_SELECTION_CHARS",
]
