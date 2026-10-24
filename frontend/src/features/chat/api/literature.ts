
/** 文献库管理、历史文献选择和文献限定 SSE API。 */

import { requestFormData, requestJson, streamEvents } from '../../../shared/api/http'
import type { StreamEventOptions } from '../../../shared/api/http'
import type { AgentEvent } from './agent'

export interface LiteratureDocument {
  document_id: string
  title: string
  source_type: 'pdf_upload' | 'pdf_url' | 'web_url'
  source_url: string | null
  file_name: string | null
  status: 'queued' | 'processing' | 'ready' | 'failed'
  error_code: string | null
  error_message: string | null
  page_count: number | null
  created_at: string
  updated_at: string
}

export interface LiteratureDocumentPage {
  items: LiteratureDocument[]
  limit: number
  offset: number
  has_more: boolean
}

export interface ConversationLiteratureDocuments {
  document_ids: string[]
  documents: LiteratureDocument[]
}

export interface LiteratureChatRequest {
  message: string
  conversation_id?: string
  document_ids?: string[]
  request_id: string
}

/** 上传 PDF 原件并创建异步入库记录。 */
export function uploadLiteraturePdf(file: File): Promise<{ document_id: string; status: string }> {
  const body = new FormData()
  body.append('file', file, file.name)
  return requestFormData('/api/v1/literature/documents', body)
}

/** 查询文献库当前页；前端状态面板请求最多 100 条。 */
export function getLiteratureDocuments(): Promise<LiteratureDocumentPage> {
  return requestJson('/api/v1/literature/documents?limit=100&offset=0')
}

/** 删除当前主体拥有的文献及其历史关联。 */
export function deleteLiteratureDocument(documentId: string): Promise<{ document_id: string; deleted: boolean }> {
  return requestJson(`/api/v1/literature/documents/${encodeURIComponent(documentId)}`, {
    method: 'DELETE',
  })
}

/** 恢复历史文献会话当前选择。 */
export function getConversationLiteratureDocuments(
  conversationId: string,
): Promise<ConversationLiteratureDocuments> {
  return requestJson(
    `/api/v1/literature/conversations/${encodeURIComponent(conversationId)}/documents`,
  )
}

/** 更新历史会话关联文献。 */
export function updateConversationLiteratureDocuments(
  conversationId: string,
  documentIds: string[],
): Promise<ConversationLiteratureDocuments> {
  return requestJson(
    `/api/v1/literature/conversations/${encodeURIComponent(conversationId)}/documents`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_ids: documentIds }),
    },
  )
}

/** 将问题和所选文献 ID 发送到专用文献问答 SSE 入口。 */
export async function streamLiteratureChat(
  payload: LiteratureChatRequest,
  onEvent: (event: AgentEvent, eventId?: string) => void,
  options: StreamEventOptions = {},
): Promise<void> {
  await streamEvents('/api/v1/literature/chat/stream', payload, onEvent, options)
}
