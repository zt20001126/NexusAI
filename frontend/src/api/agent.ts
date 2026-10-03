/** Agent 对话、追问恢复和运行取消 API。 */

import { streamAgentEvents, requestJson, type AgentEvent } from './http'

export interface ChatRequest {
  message: string
  conversation_id?: string
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
): Promise<void> {
  await streamAgentEvents('/api/agent/chat/stream', payload, onEvent)
}

export async function resumeAgentRun(
  runId: string,
  conversationId: string,
  answers: Record<string, string>,
  onEvent: (event: AgentEvent) => void,
): Promise<void> {
  await streamAgentEvents(
    `/api/agent/runs/${encodeURIComponent(runId)}/resume`,
    { conversation_id: conversationId, answers },
    onEvent,
  )
}

export function cancelAgentRun(runId: string): Promise<{ run_id: string; cancel_requested: boolean }> {
  return requestJson(`/api/agent/runs/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  })
}
