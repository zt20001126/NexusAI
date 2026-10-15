/** 会话列表和消息历史 API。 */

import { requestJson } from '../../../shared/api/http'

export interface Conversation {
  conversation_id: string
  title: string | null
  created_at: string
  updated_at: string
  agent_id: string
}

export interface TaskResultSummary {
  task_result_id: string
  agent_id: string
  result_type: string
  generation_status: 'pending' | 'awaiting_input' | 'running' | 'succeeded' | 'failed' | 'cancelled'
  image_url: string | null
  mime_type: string | null
  width: number | null
  height: number | null
  error_code: string | null
  error_message: string | null
}

export interface ConversationPage {
  items: Conversation[]
  limit: number
  offset: number
  has_more: boolean
  next_offset: number | null
}

export interface ConversationMessage {
  message_id: string
  conversation_id: string
  run_id: string | null
  sequence: number
  role: 'user' | 'assistant'
  content: string
  created_at: string
  task_results: TaskResultSummary[]
}

export interface MessagePage {
  items: ConversationMessage[]
  limit: number
  before_sequence: number | null
  next_before_sequence: number | null
}

export function getConversations(limit = 50, offset = 0): Promise<ConversationPage> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return requestJson(`/api/conversations?${query.toString()}`)
}

export function getConversationMessages(
  conversationId: string,
  limit = 50,
  beforeSequence?: number,
): Promise<MessagePage> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (beforeSequence !== undefined) query.set('before_sequence', String(beforeSequence))
  return requestJson(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages?${query.toString()}`,
  )
}
