import { useCallback, useEffect, useRef, useState } from 'react'
import type { Question } from '../api/agent'
import { cancelAgentRun, resumeAgentRun, streamChat } from '../api/agent'
import { getApiDocsUrl, type AgentEvent } from '../api/http'
import {
  getConversationMessages,
  getConversations,
  type Conversation,
} from '../api/conversations'
import ConversationSidebar from '../components/ConversationSidebar'
import Composer from '../components/Composer'
import MessageList, { type DisplayMessage, toDisplayMessage } from '../components/MessageList'
import QuestionForm from '../components/QuestionForm'

interface PendingQuestion {
  conversationId: string
  runId: string
  questions: Question[]
}

/** 对话主页面，编排会话加载、消息历史、SSE 回复和结构化追问。 */
function ChatPage() {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [draft, setDraft] = useState('')
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [conversationHasMore, setConversationHasMore] = useState(false)
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [sidebarError, setSidebarError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('随时可以开始')
  const [pendingQuestion, setPendingQuestion] = useState<PendingQuestion | null>(null)
  const [olderCursor, setOlderCursor] = useState<number | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const activeConversationRef = useRef<string | null>(null)
  const activeRunRef = useRef<string | null>(null)

  const selectConversation = useCallback((conversationId: string | null) => {
    activeConversationRef.current = conversationId
    setActiveConversationId(conversationId)
    setPendingQuestion(null)
    setError(null)
    setOlderCursor(null)
  }, [])

  const refreshConversations = useCallback(async () => {
    setSidebarError(null)
    try {
      const page = await getConversations()
      setConversations(page.items)
      setConversationHasMore(page.has_more)
      return page.items
    } catch (requestError) {
      setSidebarError(getErrorMessage(requestError))
      return null
    } finally {
      setSidebarLoading(false)
    }
  }, [])

  const refreshHistory = useCallback(async (conversationId: string) => {
    const page = await getConversationMessages(conversationId)
    if (activeConversationRef.current !== conversationId) return
    setMessages(page.items.map(toDisplayMessage))
    setOlderCursor(page.next_before_sequence)
  }, [])

  useEffect(() => {
    let mounted = true
    void getConversations()
      .then((page) => {
        if (!mounted) return
        setConversations(page.items)
        setConversationHasMore(page.has_more)
        if (page.items[0]) {
          activeConversationRef.current = page.items[0].conversation_id
          setActiveConversationId(page.items[0].conversation_id)
        }
      })
      .catch((requestError: unknown) => {
        if (mounted) setSidebarError(getErrorMessage(requestError))
      })
      .finally(() => {
        if (mounted) setSidebarLoading(false)
      })
    return () => { mounted = false }
  }, [])

  useEffect(() => {
    if (!activeConversationId) {
      setMessages([])
      setHistoryLoading(false)
      return
    }
    let current = true
    setMessages([])
    setHistoryLoading(true)
    setOlderCursor(null)
    getConversationMessages(activeConversationId)
      .then((page) => {
        if (!current) return
        setMessages(page.items.map(toDisplayMessage))
        setOlderCursor(page.next_before_sequence)
      })
      .catch((requestError: unknown) => {
        if (current) setError(getErrorMessage(requestError))
      })
      .finally(() => {
        if (current) setHistoryLoading(false)
      })
    return () => { current = false }
  }, [activeConversationId])

  const handleAgentEvent = useCallback((event: AgentEvent) => {
    activeRunRef.current = event.run_id
    if (event.conversation_id && activeConversationRef.current !== event.conversation_id) {
      activeConversationRef.current = event.conversation_id
      setActiveConversationId(event.conversation_id)
    }

    switch (event.event_type) {
      case 'run.started':
        setStatus('正在准备回复…')
        break
      case 'message.delta': {
        const content = readString(event.data.content)
        if (!content) break
        setStatus('正在回复…')
        setMessages((current) => upsertAssistantMessage(current, event.run_id, content, true, true))
        break
      }
      case 'message.completed': {
        const content = readString(event.data.content)
        if (content) setMessages((current) => upsertAssistantMessage(current, event.run_id, content, false, false))
        break
      }
      case 'tool.started':
        setStatus(`正在使用${readString(event.data.tool_name) || '工具'}…`)
        break
      case 'tool.completed':
        setStatus('正在整理结果…')
        break
      case 'question.required': {
        const questions = Array.isArray(event.data.questions)
          ? event.data.questions as Question[]
          : []
        setPendingQuestion({
          conversationId: event.conversation_id,
          runId: event.run_id,
          questions,
        })
        setStatus('等待你的补充信息')
        break
      }
      case 'run.completed':
        setPendingQuestion(null)
        activeRunRef.current = null
        setStatus('回复完成')
        break
      case 'run.cancelled':
        activeRunRef.current = null
        setStatus('已停止生成')
        break
      case 'run.failed':
        activeRunRef.current = null
        setStatus('本轮未完成')
        setError(readString(event.data.message) || '对话执行失败，请重试。')
        break
      default:
        break
    }
  }, [])

  async function finishTurn() {
    const conversationId = activeConversationRef.current
    const updatedConversations = await refreshConversations()
    if (conversationId && activeConversationRef.current === conversationId) {
      try {
        await refreshHistory(conversationId)
      } catch (requestError) {
        setError(getErrorMessage(requestError))
      }
    } else if (updatedConversations === null) {
      setSidebarError('会话列表暂时无法刷新。')
    }
  }

  async function handleSend() {
    const message = draft.trim()
    if (!message || sending) return

    const conversationId = activeConversationRef.current
    setDraft('')
    setError(null)
    setPendingQuestion(null)
    setMessages((current) => [
      ...current,
      { id: `local-${Date.now()}`, role: 'user', content: message },
    ])
    setSending(true)
    setStatus('正在连接…')

    try {
      await streamChat(
        { message, ...(conversationId ? { conversation_id: conversationId } : {}) },
        handleAgentEvent,
      )
      await finishTurn()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
      setStatus('请求未完成')
    } finally {
      activeRunRef.current = null
      setSending(false)
    }
  }

  async function handleResume(answers: Record<string, string>) {
    if (!pendingQuestion || sending) return
    setError(null)
    setSending(true)
    setStatus('正在继续处理…')
    try {
      await resumeAgentRun(
        pendingQuestion.runId,
        pendingQuestion.conversationId,
        answers,
        handleAgentEvent,
      )
      await finishTurn()
    } catch (requestError) {
      setError(getErrorMessage(requestError))
      setStatus('恢复请求未完成')
    } finally {
      activeRunRef.current = null
      setSending(false)
    }
  }

  async function handleCancel() {
    const runId = activeRunRef.current
    if (!runId) return
    try {
      await cancelAgentRun(runId)
      setStatus('正在停止…')
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  async function handleLoadOlder() {
    const conversationId = activeConversationRef.current
    if (!conversationId || olderCursor === null || loadingOlder) return
    setLoadingOlder(true)
    try {
      const page = await getConversationMessages(conversationId, 50, olderCursor)
      if (activeConversationRef.current !== conversationId) return
      setMessages((current) => [
        ...page.items.map(toDisplayMessage),
        ...current,
      ])
      setOlderCursor(page.next_before_sequence)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoadingOlder(false)
    }
  }

  async function handleLoadMoreConversations() {
    if (loadingMoreConversations || !conversationHasMore) return
    setLoadingMoreConversations(true)
    try {
      const page = await getConversations(50, conversations.length)
      setConversations((current) => [...current, ...page.items])
      setConversationHasMore(page.has_more)
    } catch (requestError) {
      setSidebarError(getErrorMessage(requestError))
    } finally {
      setLoadingMoreConversations(false)
    }
  }

  function handleNewConversation() {
    selectConversation(null)
    setMessages([])
    setError(null)
    setStatus('随时可以开始')
  }

  const activeConversation = conversations.find(
    (conversation) => conversation.conversation_id === activeConversationId,
  )

  return (
    <main className="chat-app-shell">
      <ConversationSidebar
        conversations={conversations}
        activeConversationId={activeConversationId}
        loading={sidebarLoading}
        hasMore={conversationHasMore}
        loadingMore={loadingMoreConversations}
        disabled={sending}
        error={sidebarError}
        onCreate={handleNewConversation}
        onSelect={selectConversation}
        onLoadMore={() => { void handleLoadMoreConversations() }}
        onRetry={() => { void refreshConversations() }}
      />

      <section className="chat-main">
        <header className="chat-topbar">
          <div className="topbar-title">
            <img className="mobile-brand-mark" src="/brand/nexusai-icon.png" alt="" />
            <div>
              <strong>{activeConversation?.title || (activeConversationId ? '会话' : '新对话')}</strong>
              <span><i className="status-dot" /> {status}</span>
            </div>
          </div>
          <a href={getApiDocsUrl()} target="_blank" rel="noreferrer" className="docs-link">API 文档 ↗</a>
          <button className="mobile-new-conversation" type="button" onClick={handleNewConversation} disabled={sending}>＋ 新对话</button>
        </header>

        <div className="chat-content">
          {olderCursor !== null && !historyLoading && (
            <button className="load-older-button" type="button" onClick={() => { void handleLoadOlder() }} disabled={loadingOlder}>
              {loadingOlder ? '正在加载…' : '↑ 查看更早消息'}
            </button>
          )}
          <MessageList
            messages={messages}
            loading={historyLoading}
            conversationId={activeConversationId}
          />
          {pendingQuestion && pendingQuestion.questions.length > 0 && (
            <QuestionForm
              questions={pendingQuestion.questions}
              disabled={sending}
              onSubmit={(answers) => { void handleResume(answers) }}
            />
          )}
          {error && <div className="error-banner" role="alert">{error}</div>}
        </div>

        <Composer
          value={draft}
          disabled={sending || Boolean(pendingQuestion)}
          onChange={setDraft}
          onSend={() => { void handleSend() }}
          onCancel={() => { void handleCancel() }}
          canCancel={sending && activeRunRef.current !== null}
        />
      </section>
    </main>
  )
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function upsertAssistantMessage(
  messages: DisplayMessage[],
  runId: string,
  content: string,
  append: boolean,
  streaming: boolean,
): DisplayMessage[] {
  const id = `assistant-${runId}`
  const existingIndex = messages.findIndex((message) => message.id === id)
  if (existingIndex === -1) {
    return [...messages, { id, role: 'assistant', content, streaming }]
  }
  return messages.map((message, index) => index === existingIndex
    ? { ...message, content: append ? message.content + content : content, streaming }
    : message)
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试。'
}

export default ChatPage
