/** 聊天功能使用的智能体类型和追问边界。 */
export const AgentType = {
  COMMON: 'common_agent',
  BASIC_CONVERSATION: 'basic_conversation_agent',
  IMAGE: 'image_agent',
  LISTING: 'listing_agent',
  RESEARCH: 'research_agent',
  LABOR_LAW: 'labor_law_agent',
  LITERATURE_READER: 'literature_reader_agent',
} as const
export type AgentType = typeof AgentType[keyof typeof AgentType]

export const COMMON_AGENT = AgentType.COMMON
export const IMAGE_AGENT = AgentType.IMAGE
export const LISTING_AGENT = AgentType.LISTING
export const LITERATURE_READER_AGENT = AgentType.LITERATURE_READER

const agentTypeValues = new Set<string>(Object.values(AgentType))

/** 兼容当前仍返回旧字段名 agent_id 的 API 服务。 */
export function normalizeAgentType(value: unknown): AgentType {
  if (typeof value === 'string' && agentTypeValues.has(value)) {
    return value as AgentType
  }

  throw new Error('服务端返回了无法识别的智能体类型')
}

/** 图片聊天输入的前端限制，与后端参考图约束保持一致。 */
export const MAX_REFERENCE_IMAGES = 3
export const MAX_REFERENCE_IMAGE_BYTES = 5 * 1024 * 1024
/** 追问协议的前端边界；应与后端 agent.constants 中的值保持一致。 */
export const MAX_QUESTIONS_PER_BATCH = 3
export const MAX_QUESTION_ROUNDS_PER_RUN = 3
export const MAX_QUESTION_OPTION_COUNT = 4
export const MAX_QUESTION_SELECTION_COUNT = MAX_QUESTION_OPTION_COUNT
