import type { ConversationMessage, TaskResultSummary } from '../api/conversations'
import { toDisplayQuestionAnswers } from './questionAnswers.mjs'

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
  questionAnswers?: DisplayQuestionAnswer[]
}

export interface DisplayQuestionAnswer {
  questionId: string
  title: string
  values: string[]
}

/** 将会话接口返回的消息转换为聊天视图模型。 */
export function toDisplayMessage(message: ConversationMessage): DisplayMessage {
  const blocks = message.content?.blocks ?? []
  const answerBlock = blocks.find((block) => block.type === 'question_answers')
  const questionAnswers = answerBlock?.type === 'question_answers'
    ? toDisplayQuestionAnswers(answerBlock.answers, answerBlock.question_titles)
    : []

  return {
    id: message.message_id,
    role: message.role,
    content: (questionAnswers.length > 0 ? [] : blocks)
      .filter((block): block is { type: 'text'; text: string } => block.type === 'text')
      .map((block) => block.text)
      .join('\n'),
    createdAt: message.created_at,
    taskResults: message.task_results,
    attachments: blocks
      .filter((block): block is { type: 'image'; attachment_id: string; image_url: string } => block.type === 'image')
      .map((block) => ({ attachment_id: block.attachment_id, image_url: block.image_url })),
    ...(questionAnswers.length > 0 ? { questionAnswers } : {}),
  }
}
