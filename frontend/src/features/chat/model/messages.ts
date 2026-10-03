import type { ConversationMessage } from '../api/conversations'

/** 前端聊天视图使用的消息模型。 */
export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  createdAt?: string
}

/** 将会话接口返回的消息转换为聊天视图模型。 */
export function toDisplayMessage(message: ConversationMessage): DisplayMessage {
  return {
    id: message.message_id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
  }
}
