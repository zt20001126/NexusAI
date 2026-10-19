/** 聊天功能使用的智能体类型和追问边界。 */
export enum AgentType {
  COMMON = 'common_agent',
  BASIC_CONVERSATION = 'basic_conversation_agent',
  IMAGE = 'image_agent',
  LISTING = 'listing_agent',
  RESEARCH = 'research_agent',
  LABOR_LAW = 'labor_law_agent',
  LITERATURE_READER = 'literature_reader_agent',
}

export const COMMON_AGENT = AgentType.COMMON
export const IMAGE_AGENT = AgentType.IMAGE
export const LISTING_AGENT = AgentType.LISTING
export const LITERATURE_READER_AGENT = AgentType.LITERATURE_READER

/** 图片聊天输入的前端限制，与后端参考图约束保持一致。 */
export const MAX_REFERENCE_IMAGES = 3
export const MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024
/** 追问协议的前端边界；应与后端 agent.constants 中的值保持一致。 */
export const MAX_QUESTIONS_PER_BATCH = 3
export const MAX_QUESTION_ROUNDS_PER_RUN = 3
export const MAX_QUESTION_SELECTION_COUNT = 20
export const MAX_QUESTION_ANSWER_CHARS = 2_000
export const MAX_QUESTION_SELECTION_CHARS = 500
