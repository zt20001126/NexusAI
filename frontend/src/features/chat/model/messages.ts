import type { ConversationMessage, TaskResultSummary } from '../api/conversations'
import type { Question } from '../api/agent'
import { toDisplayQuestionAnswers } from './questionAnswers.mjs'

export interface DisplayAttachment {
  attachment_id: string
  image_url: string
  previewFile?: File
}

export interface DisplayContentBlock {
  id: string
  type: 'text' | 'image' | 'question' | 'task_result'
  text?: string
  image_url?: string | null
  attachment_id?: string
  [key: string]: unknown
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
  questionBatch?: DisplayQuestionBatch
  contentBlocks?: DisplayContentBlock[]
}

export interface DisplayQuestionAnswer {
  questionId: string
  title: string
  values: string[]
}

export interface DisplayQuestionBatch {
  runId: string
  questionRound: number
  maxQuestionRounds: number
  questions: Question[]
}

/** 将会话接口返回的消息转换为聊天视图模型。 */
export function toDisplayMessage(message: ConversationMessage): DisplayMessage {
  const blocks = message.content?.blocks ?? []
  const answerBlock = blocks.find((block) => (
    (block.type === 'question' && 'answers' in block)
    || block.type === 'question_answers'
  ))
  const questionBatchBlock = blocks.find((block) => (
    (block.type === 'question' && !('answers' in block))
    || block.type === 'question_batch'
  ))
  const questionAnswers = answerBlock?.type === 'question'
    ? toDisplayQuestionAnswers(answerBlock.answers ?? {}, answerBlock.question_titles)
    : answerBlock?.type === 'question_answers'
      ? toDisplayQuestionAnswers(answerBlock.answers, answerBlock.question_titles)
      : []
  const questionBatch = questionBatchBlock && 'questions' in questionBatchBlock
    && Array.isArray(questionBatchBlock.questions)
    ? {
        runId: questionBatchBlock.run_id ?? '',
        questionRound: questionBatchBlock.question_round,
        maxQuestionRounds: questionBatchBlock.max_question_rounds,
        questions: questionBatchBlock.questions,
      }
    : undefined
  const contentBlocks = blocks.map((block, index) => ({
    ...block,
    id: 'id' in block && typeof block.id === 'string'
      ? block.id
      : `${message.message_id}-block-${index}`,
  })) as DisplayContentBlock[]
  const blockResults = contentBlocks
    .filter((block) => block.type === 'task_result' && typeof block.task_result_id === 'string')
    .map((block) => ({
      task_result_id: block.task_result_id as string,
      agent: block.agent as TaskResultSummary['agent'],
      result_type: block.result_type as string,
      generation_status: block.generation_status as TaskResultSummary['generation_status'],
      image_url: typeof block.image_url === 'string' ? block.image_url : null,
      mime_type: typeof block.mime_type === 'string' ? block.mime_type : null,
      width: typeof block.width === 'number' ? block.width : null,
      height: typeof block.height === 'number' ? block.height : null,
      error_code: typeof block.error_code === 'string' ? block.error_code : null,
      error_message: typeof block.error_message === 'string' ? block.error_message : null,
    }))
  const resultsById = new Map(
    [...message.task_results, ...blockResults].map((result) => [result.task_result_id, result]),
  )

  return {
    id: message.message_id,
    role: message.role,
    content: (questionAnswers.length > 0 || questionBatch ? [] : contentBlocks)
      .filter((block): block is DisplayContentBlock & { type: 'text'; text: string } => (
        block.type === 'text' && typeof block.text === 'string'
      ))
      .map((block) => block.text)
      .join('\n'),
    createdAt: message.created_at,
    taskResults: [...resultsById.values()],
    attachments: contentBlocks
      .filter((block) => block.type === 'image' && typeof block.image_url === 'string')
      .map((block) => ({
        attachment_id: typeof block.attachment_id === 'string' ? block.attachment_id : block.id,
        image_url: block.image_url as string,
      })),
    ...(questionAnswers.length > 0 ? { questionAnswers } : {}),
    ...(questionBatch ? { questionBatch } : {}),
    contentBlocks,
  }
}
