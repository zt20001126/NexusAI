/** 图片聊天输入的前端限制，与后端参考图约束保持一致。 */
export const MAX_REFERENCE_IMAGES = 3
export const MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024
/** 追问协议的前端边界；应与后端 agent.constants 中的值保持一致。 */
export const MAX_QUESTIONS_PER_BATCH = 5
export const MAX_QUESTION_ROUNDS_PER_RUN = 3
export const MAX_QUESTION_SELECTION_COUNT = 20
export const MAX_QUESTION_ANSWER_CHARS = 2_000
export const MAX_QUESTION_SELECTION_CHARS = 500
export const COMMON_AGENT_ID = 'common_agent'
export const IMAGE_AGENT_ID = 'image_agent'
export const LISTING_AGENT_ID = 'listing_agent'
export const LITERATURE_READER_AGENT_ID = 'literature_reader_agent'
