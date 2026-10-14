/** Agent 对话、追问恢复和运行取消 API。 */

import { requestBinary, requestJson, streamEvents } from '../../../shared/api/http'

export interface AgentEvent {
  event_id: string
  event_type: string
  conversation_id: string
  run_id: string
  sequence: number
  timestamp: string
  data: Record<string, unknown>
}

export interface ChatRequest {
  message: string
  conversation_id?: string
  attachment_ids?: string[]
}

export interface AgentDefinition {
  agent_id: string
  name: string
  description: string
  supports_image_upload: boolean
}

export interface UploadedImage {
  attachment_id: string
  file_name: string
  mime_type: string
  file_size: number
}

interface QuestionBase {
  id: string
  title: string
  prompt: string
  allow_custom_input: boolean
}

/** 交互卡片支持的题型；缺少 type 时兼容现有文本题载荷。 */
export type Question = QuestionBase & (
  | { type?: 'TextQuestion'; placeholder?: string }
  | { type: 'SingleChoice'; options: string[] }
  | { type: 'MultiChoice'; options: string[] }
  | { type: 'Confirmation' }
  | { type: 'FileUpload'; accept?: string; multiple?: boolean }
)

export async function streamChat(
  payload: ChatRequest,
  onEvent: (event: AgentEvent) => void,
  agentId = 'default',
): Promise<void> {
  await streamEvents(`/api/agents/${encodeURIComponent(agentId)}/chat/stream`, payload, onEvent)
}

export async function resumeAgentRun(
  runId: string,
  conversationId: string,
  answers: Record<string, string>,
  onEvent: (event: AgentEvent) => void,
  agentId = 'default',
): Promise<void> {
  await streamEvents(
    `/api/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}/resume`,
    { conversation_id: conversationId, answers },
    onEvent,
  )
}

export function cancelAgentRun(runId: string, agentId = 'default'): Promise<{ run_id: string; cancel_requested: boolean }> {
  return requestJson(`/api/agents/${encodeURIComponent(agentId)}/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}

export function getAgents(): Promise<AgentDefinition[]> {
  return requestJson('/api/agents')
}

export function uploadReferenceImage(file: File, agentId: string): Promise<UploadedImage> {
  const query = new URLSearchParams({ agent_id: agentId, file_name: file.name })
  return requestBinary(`/api/uploads/images?${query.toString()}`, file, file.name)
}
