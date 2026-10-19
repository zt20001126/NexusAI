import { useCallback, useEffect, useRef, useState } from 'react'
import type { Question, QuestionAnswer } from '../api/agent'
import { AgentType } from '../constants'
import {
  COMMON_AGENT,
  LITERATURE_READER_AGENT,
  MAX_QUESTION_ROUNDS_PER_RUN,
} from '../constants'
import {
  cancelAgentRun,
  getAgents,
  resumeAgentRun,
  streamChat,
  uploadReferenceImage,
} from '../api/agent'
import type { AgentDefinition, AgentEvent } from '../api/agent'
import {
  getConversationMessages,
  getConversations,
  type Conversation,
  type TaskResultSummary,
} from '../api/conversations'
import { toDisplayMessage, type DisplayMessage } from '../model/messages'
import { streamLiteratureChat } from '../api/literature'

interface PendingQuestion {
  conversationId: string
  runId: string
  questions: Question[]
  questionRound: number
  maxQuestionRounds: number
}

/** 封装聊天会话的加载、发送、恢复和事件状态更新。 */
export function useChatSession() {
  const [agents, setAgents] = useState<AgentDefinition[]>([])
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [activeAgent, setActiveAgent] = useState(COMMON_AGENT)
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [activeConversationId, setActiveConversationId] = useState<string | null>(null)
  const [messages, setMessages] = useState<DisplayMessage[]>([])
  const [sidebarLoading, setSidebarLoading] = useState(true)
  const [conversationHasMore, setConversationHasMore] = useState(false)
  const [loadingMoreConversations, setLoadingMoreConversations] = useState(false)
  const [historyLoading, setHistoryLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [sidebarError, setSidebarError] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState('随时可以开始')
  const [pendingQuestion, setPendingQuestion] = useState<PendingQuestion | null>(null)
  const [olderCursor, setOlderCursor] = useState<string | null>(null)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const activeConversationRef = useRef<string | null>(null)
  const activeRunRef = useRef<string | null>(null)
  const activeAgentRef = useRef(COMMON_AGENT)

  const selectConversation = useCallback((conversationId: string | null) => {
    activeConversationRef.current = conversationId
    setActiveConversationId(conversationId)
    const conversation = conversations.find((item) => item.conversation_id === conversationId)
    if (conversation) {
      activeAgentRef.current = conversation.agent
      setActiveAgent(conversation.agent)
    }
    setPendingQuestion(null)
    setError(null)
    setOlderCursor(null)
  }, [conversations])

  const selectAgent = useCallback((agent: AgentType) => {
    activeAgentRef.current = agent
    setActiveAgent(agent)
    activeConversationRef.current = null
    setActiveConversationId(null)
    setMessages([])
    setPendingQuestion(null)
    setError(null)
    setOlderCursor(null)
    setStatus('随时可以开始')
  }, [])

  const loadAgents = useCallback(async (isCurrent: () => boolean = () => true) => {
    setAgentsLoading(true)
    setAgentsError(null)
    try {
      const loadedAgents = await getAgents()
      if (isCurrent()) setAgents(loadedAgents)
    } catch (requestError) {
      if (isCurrent()) {
        const message = getErrorMessage(requestError)
        setAgentsError(message)
      }
    } finally {
      if (isCurrent()) setAgentsLoading(false)
    }
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
    setOlderCursor(page.next_before_message_id)
  }, [])

  useEffect(() => {
    let mounted = true
    void loadAgents(() => mounted)
    return () => { mounted = false }
  }, [loadAgents])

  useEffect(() => {
    let mounted = true
    void getConversations()
      .then((page) => {
        if (!mounted) return
        setConversations(page.items)
        setConversationHasMore(page.has_more)
        if (page.items[0]) {
          activeConversationRef.current = page.items[0].conversation_id
          activeAgentRef.current = page.items[0].agent
          setActiveAgent(page.items[0].agent)
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
        setOlderCursor(page.next_before_message_id)
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
          questionRound: readInteger(event.data.question_round) ?? 1,
          maxQuestionRounds: readInteger(event.data.max_question_rounds)
            ?? MAX_QUESTION_ROUNDS_PER_RUN,
        })
        setStatus('等待你的补充信息')
        break
      }
      case 'task_result.updated': {
        const result = readTaskResult(event.data, activeAgentRef.current)
        if (result) {
          setMessages((current) => upsertAssistantResult(current, event.run_id, result))
        }
        break
      }
      case 'run.completed':
        setPendingQuestion(null)
        activeRunRef.current = null
        setStatus('回复完成')
        break
      case 'run.cancelled':
        activeRunRef.current = null
        setPendingQuestion(null)
        setStatus('已停止生成')
        break
      case 'run.failed':
        activeRunRef.current = null
        setPendingQuestion(null)
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

  async function sendMessage(
    message: string,
    imageFiles: File[] = [],
    documentIds: string[] = [],
  ) {
    const trimmedMessage = message.trim()
    if (!trimmedMessage || sending) return

    const conversationId = activeConversationRef.current
    setError(null)
    setPendingQuestion(null)
    setSending(true)
    setStatus('正在连接…')
    let sent = false

    try {
      const uploadedImages = await Promise.all(
        imageFiles.map((file) => uploadReferenceImage(file, activeAgentRef.current)),
      )
      setMessages((current) => [
        ...current,
        {
          id: `local-${Date.now()}`,
          role: 'user',
          content: trimmedMessage,
          attachments: uploadedImages.map((item, index) => ({
            attachment_id: item.attachment_id,
            image_url: '',
            previewFile: imageFiles[index],
          })),
        },
      ])
      if (activeAgentRef.current === LITERATURE_READER_AGENT) {
        await streamLiteratureChat(
          {
            message: trimmedMessage,
            ...(conversationId ? { conversation_id: conversationId } : {}),
            document_ids: documentIds,
          },
          handleAgentEvent,
        )
      } else {
        await streamChat(
          {
            message: trimmedMessage,
            ...(conversationId ? { conversation_id: conversationId } : {}),
            ...(uploadedImages.length > 0
              ? { attachment_ids: uploadedImages.map((item) => item.attachment_id) }
              : {}),
          },
          handleAgentEvent,
          activeAgentRef.current,
        )
      }
      await finishTurn()
      sent = true
    } catch (requestError) {
      setError(getErrorMessage(requestError))
      setStatus('请求未完成')
    } finally {
      activeRunRef.current = null
      setSending(false)
    }
    return sent
  }

  async function resumeRun(answers: Record<string, QuestionAnswer>) {
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
        activeAgentRef.current,
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

  async function cancelRun() {
    const runId = activeRunRef.current
    if (!runId) return
    try {
      await cancelAgentRun(runId, activeAgentRef.current)
      setStatus('正在停止…')
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    }
  }

  async function loadOlderMessages() {
    const conversationId = activeConversationRef.current
    if (!conversationId || olderCursor === null || loadingOlder) return
    setLoadingOlder(true)
    try {
      const page = await getConversationMessages(conversationId, 50, olderCursor)
      if (activeConversationRef.current !== conversationId) return
      setMessages((current) => [...page.items.map(toDisplayMessage), ...current])
      setOlderCursor(page.next_before_message_id)
    } catch (requestError) {
      setError(getErrorMessage(requestError))
    } finally {
      setLoadingOlder(false)
    }
  }

  async function loadMoreConversations() {
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

  const activeConversation = conversations.find(
    (conversation) => conversation.conversation_id === activeConversationId,
  )

  return {
    agents,
    agentsLoading,
    agentsError,
    loadAgents,
    activeAgent,
    conversations,
    activeConversation,
    activeConversationId,
    messages,
    sidebarLoading,
    conversationHasMore,
    loadingMoreConversations,
    historyLoading,
    sending,
    sidebarError,
    error,
    status,
    pendingQuestion,
    olderCursor,
    loadingOlder,
    canCancel: sending && activeRunRef.current !== null,
    selectConversation,
    selectAgent,
    refreshConversations,
    sendMessage,
    resumeRun,
    cancelRun,
    loadOlderMessages,
    loadMoreConversations,
  }
}

function readTaskResult(data: Record<string, unknown>, agent: AgentType): TaskResultSummary | null {
  const taskResultId = readString(data.task_result_id)
  const status = readString(data.generation_status)
  const allowedStatuses = ['pending', 'awaiting_input', 'running', 'succeeded', 'failed', 'cancelled']
  if (!taskResultId || !allowedStatuses.includes(status)) return null
  return {
    task_result_id: taskResultId,
    agent: readAgent(data.agent, agent),
    result_type: readString(data.result_type) || 'image',
    generation_status: status as TaskResultSummary['generation_status'],
    image_url: readNullableString(data.image_url),
    mime_type: readNullableString(data.mime_type),
    width: readNullableNumber(data.width),
    height: readNullableNumber(data.height),
    error_code: readNullableString(data.error_code),
    error_message: readNullableString(data.error_message),
  }
}

function readAgent(value: unknown, fallback: AgentType): AgentType {
  return Object.values(AgentType).find((agent) => agent === value) ?? fallback
}

function upsertAssistantResult(
  messages: DisplayMessage[],
  runId: string,
  result: TaskResultSummary,
): DisplayMessage[] {
  const id = `assistant-${runId}`
  const existingIndex = messages.findIndex((message) => message.id === id)
  if (existingIndex === -1) {
    return [...messages, { id, role: 'assistant', content: '', taskResults: [result] }]
  }
  return messages.map((message, index) => {
    if (index !== existingIndex) return message
    const results = message.taskResults ?? []
    return {
      ...message,
      taskResults: [
        ...results.filter((item) => item.task_result_id !== result.task_result_id),
        result,
      ],
    }
  })
}

function readNullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function readNullableNumber(value: unknown): number | null {
  return typeof value === 'number' ? value : null
}

function readString(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function readInteger(value: unknown): number | null {
  return typeof value === 'number' && Number.isInteger(value) && value > 0 ? value : null
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
  if (existingIndex === -1) return [...messages, { id, role: 'assistant', content, streaming }]
  return messages.map((message, index) => index === existingIndex
    ? { ...message, content: append ? message.content + content : content, streaming }
    : message)
}

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试。'
}
