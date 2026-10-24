
import { useCallback, useEffect, useRef, useState } from 'react'
import {
  deleteLiteratureDocument,
  getConversationLiteratureDocuments,
  getLiteratureDocuments,
  updateConversationLiteratureDocuments,
  uploadLiteraturePdf,
  type LiteratureDocument,
} from '../api/literature'

interface LiteratureLibraryPanelProps {
  conversationId: string | null
  assistantResponseId: string | null
  sending: boolean
  disabled: boolean
  onSelectedDocumentIdsChange: (documentIds: string[]) => void
}

/** 管理文献导入、处理状态和当前会话可检索文献选择。 */
function LiteratureLibraryPanel({
  conversationId,
  assistantResponseId,
  sending,
  disabled,
  onSelectedDocumentIdsChange,
}: LiteratureLibraryPanelProps) {
  const [documents, setDocuments] = useState<LiteratureDocument[]>([])
  const [selectedIds, setSelectedIds] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [collapsed, setCollapsed] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const onSelectedDocumentIdsChangeRef = useRef(onSelectedDocumentIdsChange)
  const previousConversationIdRef = useRef(conversationId)
  const previousAssistantResponseIdRef = useRef<string | null>(null)
  const previousSendingRef = useRef(sending)
  const collapsedForCurrentResponseRef = useRef(false)
  const uploadedDocumentRef = useRef<{ id: string; fileName: string } | null>(null)

  useEffect(() => {
    if (sending && !previousSendingRef.current) {
      collapsedForCurrentResponseRef.current = false
    }

    if (previousConversationIdRef.current !== conversationId) {
      previousConversationIdRef.current = conversationId
      previousAssistantResponseIdRef.current = assistantResponseId
      setCollapsed(false)
      if (sending && assistantResponseId && !collapsedForCurrentResponseRef.current) {
        setCollapsed(true)
        collapsedForCurrentResponseRef.current = true
      }
      previousSendingRef.current = sending
      return
    }

    if (!assistantResponseId && previousAssistantResponseIdRef.current) {
      setCollapsed(false)
    } else if (assistantResponseId && assistantResponseId !== previousAssistantResponseIdRef.current) {
      if (!sending || !collapsedForCurrentResponseRef.current) {
        setCollapsed(true)
        if (sending) collapsedForCurrentResponseRef.current = true
      }
    }
    previousAssistantResponseIdRef.current = assistantResponseId
    previousSendingRef.current = sending
  }, [assistantResponseId, conversationId, sending])

  useEffect(() => {
    onSelectedDocumentIdsChangeRef.current = onSelectedDocumentIdsChange
  }, [onSelectedDocumentIdsChange])

  const refreshDocuments = useCallback(async () => {
    try {
      const page = await getLiteratureDocuments()
      setDocuments(page.items)
      const uploadedDocument = uploadedDocumentRef.current
      if (uploadedDocument) {
        const current = page.items.find((item) => item.document_id === uploadedDocument.id)
        if (current?.status === 'ready') {
          setNotice(`《${uploadedDocument.fileName}》已完成解析，可用于回答。`)
          uploadedDocumentRef.current = null
        } else if (current?.status === 'failed') {
          setNotice(`《${uploadedDocument.fileName}》解析失败，请查看下方错误。`)
          uploadedDocumentRef.current = null
        }
      }
      setError(null)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refreshDocuments()
    const timer = window.setInterval(() => { void refreshDocuments() }, 3_000)
    return () => window.clearInterval(timer)
  }, [refreshDocuments])

  useEffect(() => {
    let current = true
    setSelectedIds([])
    onSelectedDocumentIdsChangeRef.current([])
    if (!conversationId) return () => { current = false }

    void getConversationLiteratureDocuments(conversationId)
      .then((result) => {
        if (!current) return
        setSelectedIds(result.document_ids)
        onSelectedDocumentIdsChangeRef.current(result.document_ids)
      })
      .catch((requestError: unknown) => {
        if (current) setError(getErrorMessage(requestError))
      })
    return () => { current = false }
  }, [conversationId])

  async function saveSelection(nextIds: string[]) {
    setSelectedIds(nextIds)
    onSelectedDocumentIdsChangeRef.current(nextIds)
    setError(null)
    if (!conversationId) return
    try {
      const result = await updateConversationLiteratureDocuments(conversationId, nextIds)
      setSelectedIds(result.document_ids)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  async function handleUpload(file: File | undefined) {
    if (!file) return
    setBusy(true)
    setError(null)
    setNotice(null)
    try {
      const uploaded = await uploadLiteraturePdf(file)
      uploadedDocumentRef.current = { id: uploaded.document_id, fileName: file.name }
      setNotice(`已提交《${file.name}》，正在解析。`)
      await refreshDocuments()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(document: LiteratureDocument) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await deleteLiteratureDocument(document.document_id)
      const nextIds = selectedIds.filter((id) => id !== document.document_id)
      await saveSelection(nextIds)
      await refreshDocuments()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setBusy(false)
    }
  }

  function toggleDocument(documentId: string, checked: boolean) {
    const nextIds = checked
      ? [...selectedIds, documentId]
      : selectedIds.filter((item) => item !== documentId)
    void saveSelection(nextIds)
  }

  if (collapsed) {
    return (
      <button
        className="literature-collapsed-bar"
        type="button"
        aria-expanded="false"
        aria-label="展开文献库与回答依据"
        onClick={() => setCollapsed(false)}
      >
        <span className="literature-collapsed-label">本次回答依据</span>
        <span className="literature-collapsed-summary">已选 {selectedIds.length} 篇</span>
        <span className="literature-collapsed-expand">
          展开 <i className="literature-chevron" aria-hidden="true" />
        </span>
      </button>
    )
  }

  return (
    <section className="literature-panel" aria-label="文献库与文献选择">
      <div className="literature-panel-heading">
        <div>
          <strong>本次回答依据</strong>
          <span>只检索勾选且处理完成的文献</span>
        </div>
        <div className="literature-panel-heading-actions">
          <button
            type="button"
            className="literature-upload-button"
            disabled={disabled || busy}
            onClick={() => fileInputRef.current?.click()}
          >
            <span aria-hidden="true">＋</span> 上传 PDF
          </button>
          <input
            ref={fileInputRef}
            className="literature-file-input"
            type="file"
            accept="application/pdf,.pdf"
            disabled={disabled || busy}
            onChange={(event) => {
              void handleUpload(event.currentTarget.files?.[0])
              event.currentTarget.value = ''
            }}
            aria-label="上传 PDF 文献"
          />
          <span className="literature-selected-count">已选 {selectedIds.length} 篇</span>
          <button
            className="literature-collapse-button"
            type="button"
            aria-expanded="true"
            aria-label="收起文献库"
            onClick={() => setCollapsed(true)}
          >
            <i className="literature-chevron" aria-hidden="true" />
          </button>
        </div>
      </div>

      {notice && <p className="literature-notice" role="status">{notice}</p>}
      {error && <p className="literature-error" role="alert">{error}</p>}
      {loading && documents.length === 0 ? (
        <p className="literature-empty">正在读取文献库…</p>
      ) : documents.length === 0 ? (
        <p className="literature-empty">还没有文献。上传 PDF 后即可开始提问。</p>
      ) : (
        <div className="literature-document-list">
          {documents.map((document) => (
            <article className="literature-document" key={document.document_id}>
              <label className="literature-document-select">
                <input
                  type="checkbox"
                  checked={selectedIds.includes(document.document_id)}
                  disabled={disabled || busy || document.status !== 'ready'}
                  onChange={(event) => toggleDocument(document.document_id, event.target.checked)}
                />
                <span className="literature-document-copy">
                  <strong title={document.title}>{document.title}</strong>
                  <span>{document.page_count ? `${document.page_count} 页 · ` : ''}{statusText(document.status)}</span>
                  {document.error_message && (
                    <span className="literature-document-error">{document.error_message}</span>
                  )}
                </span>
              </label>
              <button
                className="literature-delete-button"
                type="button"
                onClick={() => { void handleDelete(document) }}
                disabled={disabled || busy}
                aria-label={`删除 ${document.title}`}
              >
                删除
              </button>
            </article>
          ))}
        </div>
      )}
      <p className="literature-selection-hint">新问题至少需要一篇已就绪文献。</p>
    </section>
  )
}

function statusText(status: LiteratureDocument['status']): string {
  switch (status) {
    case 'queued': return '排队中'
    case 'processing': return '处理中'
    case 'ready': return '可用于回答'
    case 'failed': return '处理失败'
  }
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '文献操作失败，请稍后重试。'
}

export default LiteratureLibraryPanel
