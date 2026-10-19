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
  role: 'user' | 'assistant'
  content: {
    blocks: Array<
      | { type: 'text'; text: string }
      | { type: 'image'; attachment_id: string; image_url: string }
      | { type: 'question_answers'; answers: Record<string, unknown> }
    >
  }
  created_at: string
  task_results: TaskResultSummary[]
}

export interface MessagePage {
  items: ConversationMessage[]
  limit: number
  before_message_id: string | null
  next_before_message_id: string | null
}

export function getConversations(limit = 50, offset = 0): Promise<ConversationPage> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  return requestJson(`/api/conversations?${query.toString()}`)
}

export function getConversationMessages(
  conversationId: string,
  limit = 50,
  beforeMessageId?: string,
): Promise<MessagePage> {
  const query = new URLSearchParams({ limit: String(limit) })
  if (beforeMessageId !== undefined) query.set('before_message_id', beforeMessageId)
  return requestJson(
    `/api/conversations/${encodeURIComponent(conversationId)}/messages?${query.toString()}`,
  )
}
