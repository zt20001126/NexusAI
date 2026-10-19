import type { ConversationMessage, TaskResultSummary } from '../api/conversations'

export interface DisplayAttachment {
  attachment_id: string
  image_url: string
  previewFile?: File
}

/** 前端聊天视图使用的消息模型。 */
export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  createdAt?: string
  taskResults?: TaskResultSummary[]
  attachments?: DisplayAttachment[]
}

/** 将会话接口返回的消息转换为聊天视图模型。 */
export function toDisplayMessage(message: ConversationMessage): DisplayMessage {
  return {
    id: message.message_id,
    role: message.role,
    content: (message.content?.blocks ?? [])
      .filter((block): block is { type: 'text'; text: string } => block.type === 'text')
      .map((block) => block.text)
      .join('\n'),
    createdAt: message.created_at,
    taskResults: message.task_results,
    attachments: (message.content?.blocks ?? [])
      .filter((block): block is { type: 'image'; attachment_id: string; image_url: string } => block.type === 'image')
      .map((block) => ({ attachment_id: block.attachment_id, image_url: block.image_url })),
  }
}
