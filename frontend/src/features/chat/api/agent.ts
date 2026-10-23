/** Agent 对话、追问恢复和运行取消 API。 */

import { requestBinary, requestJson, streamEvents } from '../../../shared/api/http'
import type { StreamEventOptions } from '../../../shared/api/http'
import { COMMON_AGENT, normalizeAgentType, type AgentType } from '../constants'

export type RunTerminalStatus = 'completed' | 'waiting' | 'cancelled' | 'failed'
export type ToolStatus = 'started' | 'completed'

export interface PublicMessageBlock {
  id: string
  type: 'text' | 'image' | 'question' | 'task_result'
  text?: string
  image_url?: string | null
  attachment_id?: string
  task_result_id?: string
  agent?: AgentType
  result_type?: string
  generation_status?: string
  question_round?: number
  max_question_rounds?: number
  questions?: Question[]
  answers?: Record<string, QuestionAnswer>
  question_titles?: Record<string, string>
  [key: string]: unknown
}

export interface MessageDeltaData {
  operation: 'delta'
  message_id: string
  block_id: string
  offset: number
  text: string
}

export interface MessageSnapshotData {
  operation: 'snapshot'
  message_id: string
  content: { blocks: PublicMessageBlock[] }
}

export interface AgentEventEnvelope {
  event_id: string
  timestamp: string
}

export type AgentEvent = AgentEventEnvelope & (
  | { event_type: 'heartbeat' | 'start'; data: Record<string, never> }
  | { event_type: 'message'; data: MessageDeltaData | MessageSnapshotData }
  | {
      event_type: 'status'
      data: {
        status: ToolStatus
        tool_name: string
        tool_call_id?: string
        success?: boolean
      }
    }
  | {
      event_type: 'end'
      data: {
        status: RunTerminalStatus
        error?: { code: string; message: string }
      }
    }
)

export type AgentEventType = AgentEvent['event_type']

export interface ChatRequest {
  message: string
  conversation_id?: string
  attachment_ids?: string[]
  request_id: string
}

export interface AgentDefinition {
  agent: AgentType
  name: string
  description: string
  supports_image_upload: boolean
  supports_document_upload: boolean
}

type AgentDefinitionResponse = Omit<AgentDefinition, 'agent'> & {
  agent?: unknown
  agent_id?: unknown
}

export interface UploadedImage {
  attachment_id: string
  file_name: string
  mime_type: string
  file_size: number
}

export interface ListingOutputVersion {
  version: number
  title: string
  selling_points: string[]
  description: string
  keywords: string[]
  product_attributes: Record<string, string>
}

export interface ListingTaskResult {
  task_result_id: string
  agent: AgentType
  result_type: 'listing'
  generation_status: string
  result_data: {
    schema_version: string
    product_facts: Record<string, unknown>
    image_analysis: Record<string, unknown>
    versions: ListingOutputVersion[]
  }
}

/** 追问答案保持文本或多选值数组，避免使用换行分隔的隐式格式。 */
export type QuestionAnswer = string | string[]

export interface QuestionOption {
  label: string
  description: string
}

/** 全项目统一的结构化题卡协议。 */
export interface Question {
  id: string
  title: string
  type: 'SingleChoice' | 'MultiChoice'
  options: [QuestionOption, QuestionOption, QuestionOption, QuestionOption]
  allow_custom_input: false
}

export async function streamChat(
  payload: ChatRequest,
  onEvent: (event: AgentEvent, eventId?: string) => void,
  agent: AgentType = COMMON_AGENT,
  options: StreamEventOptions = {},
): Promise<void> {
  await streamEvents(`/api/agents/${encodeURIComponent(agent)}/chat/stream`, payload, onEvent, options)
}

/** 监听已存在运行的 Redis Stream，并从浏览器最后保存的游标续接。 */
export async function listenAgentRun(
  conversationId: string,
  runId: string,
  after: string | null,
  onEvent: (event: AgentEvent, eventId?: string) => void,
  options: Omit<StreamEventOptions, 'run'> = {},
): Promise<void> {
  await streamEvents('', null, onEvent, {
    ...options,
    run: { conversationId, runId, after },
  })
}

export async function resumeAgentRun(
  runId: string,
  conversationId: string,
  answers: Record<string, QuestionAnswer>,
  onEvent: (event: AgentEvent, eventId?: string) => void,
  agent: AgentType = COMMON_AGENT,
  options: StreamEventOptions = {},
  afterEventId: string | null = null,
  requestId: string = createRequestId(),
): Promise<void> {
  await streamEvents(
    `/api/agents/${encodeURIComponent(agent)}/runs/${encodeURIComponent(runId)}/resume`,
    {
      conversation_id: conversationId,
      answers,
      request_id: requestId,
      after_event_id: afterEventId,
    },
    onEvent,
    options,
  )
}

function createRequestId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}_${Math.random().toString(36).slice(2).padEnd(16, '0')}`
}

export function cancelAgentRun(runId: string, agent: AgentType = COMMON_AGENT): Promise<{ run_id: string; cancel_requested: boolean }> {
  return requestJson(`/api/agents/${encodeURIComponent(agent)}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export async function getAgents(): Promise<AgentDefinition[]> {
  const definitions = await requestJson<AgentDefinitionResponse[]>('/api/agents')
  return definitions.map(({ agent, agent_id, ...definition }) => ({
    ...definition,
    agent: normalizeAgentType(agent ?? agent_id),
  }))
}

export function getListingTaskResult(taskResultId: string): Promise<ListingTaskResult> {
  return requestJson('/api/task-results/' + encodeURIComponent(taskResultId))
}

export function uploadReferenceImage(file: File, agent: AgentType): Promise<UploadedImage> {
  const query = new URLSearchParams({ agent: agent, file_name: file.name })
  return requestBinary(`/api/uploads/images?${query.toString()}`, file, file.name)
}
