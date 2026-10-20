/** 会话列表和消息历史 API。 */

import { requestJson } from '../../../shared/api/http'
import type { Question } from './agent'
import { normalizeAgentType, type AgentType } from '../constants'

export interface Conversation {
  conversation_id: string
  title: string | null
  created_at: string
  updated_at: string
  agent: AgentType
}

export interface TaskResultSummary {
  task_result_id: string
  agent: AgentType
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

type ConversationResponse = Omit<Conversation, 'agent'> & {
  agent?: unknown
  agent_id?: unknown
}

type ConversationPageResponse = Omit<ConversationPage, 'items'> & {
  items: ConversationResponse[]
}

export interface ConversationMessage {
  message_id: string
  conversation_id: string
  role: 'user' | 'assistant'
  content: {
    blocks: Array<
      | { id?: string; type: 'text'; text: string }
      | { id?: string; type: 'image'; attachment_id?: string; image_url: string }
      | {
          id?: string
          type: 'question'
          run_id?: string
          question_round: number
          max_question_rounds: number
          questions: Question[]
          answers?: Record<string, unknown>
          question_titles?: Record<string, string>
        }
      | {
          id?: string
          type: 'task_result'
          task_result_id: string
          agent: AgentType
          result_type: string
          generation_status: TaskResultSummary['generation_status']
          image_url?: string | null
          error_code?: string | null
          error_message?: string | null
        }
      | {
          type: 'question_answers'
          answers: Record<string, unknown>
          question_titles?: Record<string, string>
        }
      | {
          type: 'question_batch'
          run_id: string
          question_round: number
          max_question_rounds: number
          questions: Question[]
        }
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

export interface ActiveAgentRun {
  conversation_id: string
  run_id: string
  agent: AgentType
  status: 'queued' | 'running'
  last_event_id: string | null
}

export interface AgentRunStatus {
  conversation_id: string
  run_id: string
  status: 'queued' | 'running' | 'waiting' | 'completed' | 'cancelled' | 'failed'
  last_event_id: string | null
  error: string | null
}

/** 页面刷新后恢复当前主体全部后台 Agent 运行。 */
export function getActiveAgentRuns(): Promise<{ items: ActiveAgentRun[] }> {
  return requestJson('/api/conversations/active')
}

/** 查询指定会话最近一轮运行的后台生命周期和事件游标。 */
export function getConversationRunStatus(
  conversationId: string,
  runId?: string,
): Promise<AgentRunStatus> {
  const query = new URLSearchParams()
  if (runId) query.set('run_id', runId)
  const suffix = query.size ? `?${query.toString()}` : ''
  return requestJson(`/api/conversations/${encodeURIComponent(conversationId)}/status${suffix}`)
}

export async function getConversations(limit = 50, offset = 0): Promise<ConversationPage> {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset) })
  const page = await requestJson<ConversationPageResponse>(`/api/conversations?${query.toString()}`)
  return {
    ...page,
    items: page.items.map(({ agent, agent_id, ...conversation }) => ({
      ...conversation,
      agent: normalizeAgentType(agent ?? agent_id),
    })),
  }
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
