"""共享智能体标识与输入边界常量。"""

# 注册表、持久化和前端 API 共用的稳定智能体标识。
COMMON_AGENT_ID = "common_agent"
IMAGE_AGENT_ID = "image_agent"
LISTING_AGENT_ID = "listing_agent"
RESEARCH_AGENT_ID = "research_agent"

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

__all__ = [
    "COMMON_AGENT_ID",
    "IMAGE_AGENT_ID",
    "CHECKPOINT_AGENT_NAMESPACE_COMPATIBILITY",
    "LISTING_AGENT_ID",
    "RESEARCH_AGENT_ID",
    "MAX_REFERENCE_IMAGE_BYTES",
    "MAX_REFERENCE_IMAGE_COUNT",
    "MAX_REFERENCE_IMAGE_TOTAL_BYTES",
]
