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
  listenAgentRun,
  resumeAgentRun,
  streamChat,
  uploadReferenceImage,
} from '../api/agent'
import type {
  AgentDefinition,
  AgentEvent,
  RunTerminalStatus,
  UploadedImage,
} from '../api/agent'
import {
  getConversationMessages,
  getActiveAgentRuns,
  getConversationRunStatus,
  getConversations,
  type Conversation,
  type TaskResultSummary,
} from '../api/conversations'
import {
  toDisplayMessage,
  type DisplayContentBlock,
  type DisplayMessage,
} from '../model/messages'
import { streamLiteratureChat } from '../api/literature'
import { ApiRequestError } from '../../../shared/api/http'

interface PendingQuestion {
  conversationId: string
  runId: string
  questions: Question[]
  questionRound: number
  maxQuestionRounds: number
}

interface RetryableChatSubmission {
  signature: string
  requestId: string
  uploadedImages: UploadedImage[]
}

interface RetryableResumeSubmission {
  signature: string
  requestId: string
}

function readRunTerminalOutcome(event: AgentEvent): RunTerminalStatus | null {
  if (event.event_type !== 'end') return null
  const status = readString(event.data.status)
  return status === 'completed' || status === 'waiting' || status === 'cancelled' || status === 'failed'
    ? status
    : null
}

/** 封装聊天会话的加载、发送、恢复和事件状态更新。 */
export function useChatSession() {
  const [agents, setAgents] = useState<AgentDefinition[]>([])
  const [agentsLoading, setAgentsLoading] = useState(true)
  const [agentsError, setAgentsError] = useState<string | null>(null)
  const [activeAgent, setActiveAgent] = useState<AgentType>(COMMON_AGENT)
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
  const activeAgentRef = useRef<AgentType>(COMMON_AGENT)
  const runByConversationRef = useRef(new Map<string, string>())
  const listenerControllerRef = useRef<AbortController | null>(null)
  const listenerKeyRef = useRef<string | null>(null)
  const liveRunKeysRef = useRef(new Set<string>())
  const retryableSubmissionRef = useRef<RetryableChatSubmission | null>(null)
  const retryableResumeRef = useRef<RetryableResumeSubmission | null>(null)
  const handleAgentEventRef = useRef<(
    (event: AgentEvent, conversationId?: string, runId?: string) => void
  ) | null>(null)

  const detachCurrentListener = useCallback(() => {
    const key = listenerKeyRef.current
    if (key) liveRunKeysRef.current.delete(key)
    listenerControllerRef.current?.abort()
    listenerControllerRef.current = null
    listenerKeyRef.current = null
  }, [])

  const selectConversation = useCallback((conversationId: string | null) => {
    if (conversationId === activeConversationRef.current) return
    detachCurrentListener()
    activeConversationRef.current = conversationId
    activeRunRef.current = conversationId
      ? runByConversationRef.current.get(conversationId) ?? null
      : null
    setActiveConversationId(conversationId)
    const conversation = conversations.find((item) => item.conversation_id === conversationId)
    if (conversation) {
      activeAgentRef.current = conversation.agent
      setActiveAgent(conversation.agent)
    }
    setPendingQuestion(null)
    setError(null)
    setOlderCursor(null)
    setSending(false)
  }, [conversations, detachCurrentListener])

  const selectAgent = useCallback((agent: AgentType) => {
    detachCurrentListener()
    activeRunRef.current = null
    activeAgentRef.current = agent
    setActiveAgent(agent)
    activeConversationRef.current = null
    setActiveConversationId(null)
    setMessages([])
    setPendingQuestion(null)
    setError(null)
    setOlderCursor(null)
    setStatus('随时可以开始')
    setSending(false)
  }, [detachCurrentListener])

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
      .then(async (page) => {
        if (!mounted) return
        setConversations(page.items)
        setConversationHasMore(page.has_more)
        let activeRun
        try {
          activeRun = (await getActiveAgentRuns()).items[0]
        } catch {
          // Redis 暂时不可用时仍打开历史会话；用户可稍后重新进入运行会话。
          activeRun = undefined
        }
        if (!mounted) return
        if (activeRun) {
          runByConversationRef.current.set(activeRun.conversation_id, activeRun.run_id)
          activeRunRef.current = activeRun.run_id
        }
        const selectedConversationId = activeRun?.conversation_id ?? page.items[0]?.conversation_id
        if (selectedConversationId) {
          activeConversationRef.current = selectedConversationId
          const selectedConversation = page.items.find(
            (item) => item.conversation_id === selectedConversationId,
          )
          const selectedAgent = activeRun?.agent ?? selectedConversation?.agent ?? COMMON_AGENT
          activeAgentRef.current = selectedAgent
          setActiveAgent(selectedAgent)
          setActiveConversationId(selectedConversationId)
          if (activeRun) setStatus('正在恢复后台生成…')
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
    let controller: AbortController | null = null
    setMessages([])
    setHistoryLoading(true)
    setOlderCursor(null)
    const conversationId = activeConversationId
    void getConversationMessages(conversationId)
      .then(async (page) => {
        if (!current) return
        setMessages(page.items.map(toDisplayMessage))
        setOlderCursor(page.next_before_message_id)
        const savedQuestion = [...page.items].reverse().find((item) =>
          item.role === 'assistant'
          && item.content.blocks.some((block) => (
            block.type === 'question_batch'
            || (block.type === 'question' && 'questions' in block && !('answers' in block))
          )),
        )?.content.blocks.find((block) => (
          block.type === 'question_batch'
          || (block.type === 'question' && 'questions' in block && !('answers' in block))
        ))
        try {
          const run = await getConversationRunStatus(conversationId)
          if (!current) return
          if (run.status === 'waiting' && savedQuestion && 'questions' in savedQuestion) {
            setPendingQuestion({
              conversationId,
              runId: savedQuestion.run_id ?? run.run_id,
              questions: savedQuestion.questions,
              questionRound: savedQuestion.question_round,
              maxQuestionRounds: savedQuestion.max_question_rounds,
            })
          } else if (run.status !== 'queued' && run.status !== 'running') {
            setPendingQuestion(null)
            setStatus(run.status === 'waiting' ? '等待你的补充信息'
              : run.status === 'cancelled' ? '已停止生成'
                : run.status === 'failed' ? '本轮未完成' : '随时可以开始')
          }
          runByConversationRef.current.set(conversationId, run.run_id)
          if (run.status !== 'queued' && run.status !== 'running') {
            if (activeConversationRef.current === conversationId) activeRunRef.current = null
            return
          }
          const key = `${conversationId}:${run.run_id}`
          activeRunRef.current = run.run_id
          setStatus(run.status === 'queued' ? '正在排队…' : '正在恢复后台生成…')
          if (liveRunKeysRef.current.has(key)) return
          // 历史消息已从数据库恢复到本次查询时刻；从 Redis 最新游标继续，
          // 避免把已经合并进历史快照的旧 delta 再追加一次。
          const after = run.last_event_id
          controller = new AbortController()
          listenerControllerRef.current = controller
          listenerKeyRef.current = key
          liveRunKeysRef.current.add(key)
          setSending(true)
          void listenAgentRun(conversationId, run.run_id, after, (event) => {
            handleAgentEventRef.current?.(event, conversationId, run.run_id)
          }, {
            signal: controller.signal,
            onEventId: (eventId) => saveRunCursor(conversationId, run.run_id, eventId),
            onExpired: async () => {
              clearRunCursor(conversationId, run.run_id)
              await refreshHistory(conversationId)
              const latest = await getConversationRunStatus(conversationId, run.run_id)
              return latest.status === 'queued' || latest.status === 'running'
                ? latest.last_event_id
                : null
            },
          }).then(async () => {
            if (current && activeConversationRef.current === conversationId) {
              await refreshHistory(conversationId)
            }
          }).catch((requestError: unknown) => {
            if (current && !controller?.signal.aborted) setError(getErrorMessage(requestError))
          }).finally(() => {
            liveRunKeysRef.current.delete(key)
            if (listenerControllerRef.current === controller) {
              listenerControllerRef.current = null
              listenerKeyRef.current = null
              setSending(false)
            }
          })
        } catch (requestError) {
          // 没有任何历史运行时 404 是正常状态，不覆盖已经加载的会话记录。
          if (current && getErrorMessage(requestError).includes('运行记录')) return
          if (current) setError(getErrorMessage(requestError))
        }
      })
      .catch((requestError: unknown) => {
        if (current) setError(getErrorMessage(requestError))
      })
      .finally(() => {
        if (current) setHistoryLoading(false)
      })
    return () => {
      current = false
      if (controller && listenerControllerRef.current === controller) detachCurrentListener()
    }
  }, [activeConversationId, detachCurrentListener, refreshHistory])

  const handleAgentEvent = useCallback((
    event: AgentEvent,
    eventConversationId?: string,
    eventRunId?: string,
  ) => {
    const conversationId = eventConversationId ?? activeConversationRef.current
    const runId = eventRunId ?? activeRunRef.current
    if (!conversationId || !runId) return
    runByConversationRef.current.set(conversationId, runId)
    if (activeConversationRef.current !== conversationId) return
    activeRunRef.current = runId

    const terminalOutcome = readRunTerminalOutcome(event)
    if (terminalOutcome === 'completed' || terminalOutcome === 'cancelled' || terminalOutcome === 'failed') {
      window.dispatchEvent(new Event('nexusai:credits-changed'))
    }
    if (terminalOutcome === 'completed') {
      setPendingQuestion(null)
      if (activeRunRef.current === runId) activeRunRef.current = null
      setMessages((current) => current.map((message) => ({ ...message, streaming: false })))
      setStatus('回复完成')
      return
    }
    if (terminalOutcome === 'waiting') {
      setMessages((current) => current.map((message) => ({ ...message, streaming: false })))
      setStatus('等待你的补充信息')
      return
    }
    if (terminalOutcome === 'cancelled') {
      if (activeRunRef.current === runId) activeRunRef.current = null
      setPendingQuestion(null)
      setMessages((current) => current.map((message) => ({ ...message, streaming: false })))
      setStatus('已停止生成')
      return
    }
    if (terminalOutcome === 'failed') {
      if (activeRunRef.current === runId) activeRunRef.current = null
      setPendingQuestion(null)
      setMessages((current) => current.map((message) => ({ ...message, streaming: false })))
      setStatus('本轮未完成')
      const error = event.event_type === 'end' ? event.data.error : undefined
      setError(
        error && typeof error === 'object' && 'message' in error
          ? readString(error.message)
          : '对话执行失败，请重试。',
      )
      return
    }

    switch (event.event_type) {
      case 'start':
        setStatus('正在准备回复…')
        break
      case 'heartbeat':
        break
      case 'message': {
        if (event.data.operation === 'delta') {
          const { message_id: messageId, block_id: blockId, offset, text } = event.data
          if (!messageId || !blockId || !text || !Number.isInteger(offset) || offset < 0) break
          setStatus('正在回复…')
          setMessages((current) => upsertAssistantDelta(
            current, messageId, blockId, offset, text,
          ))
          break
        }
        const messageId = event.data.message_id
        const blocks: DisplayContentBlock[] = event.data.content.blocks.map((block) => (
          block.type === 'question' && !readString(block.run_id)
            ? { ...block, run_id: runId }
            : block
        ))
        setMessages((current) => upsertAssistantSnapshot(
          current, messageId, blocks, activeAgentRef.current,
        ))
        const question = blocks.find((block) => block.type === 'question' && Array.isArray(block.questions))
        if (question && Array.isArray(question.questions)) {
          setPendingQuestion({
            conversationId,
            runId,
            questions: question.questions as Question[],
            questionRound: readInteger(question.question_round) ?? 1,
            maxQuestionRounds: readInteger(question.max_question_rounds)
              ?? MAX_QUESTION_ROUNDS_PER_RUN,
          })
          setStatus('等待你的补充信息')
        } else if (blocks.some((block) => block.type === 'text')) {
          setStatus('正在回复…')
        }
        break
      }
      case 'status':
        if (event.data.status === 'started') {
          setStatus(`正在使用${readString(event.data.tool_name) || '工具'}…`)
        } else if (event.data.status === 'completed') {
          setStatus('正在整理结果…')
        }
        break
      default:
        break
    }
  }, [])

  handleAgentEventRef.current = handleAgentEvent

  async function finishTurn(conversationId = activeConversationRef.current) {
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
    const submittedAgent = activeAgentRef.current
    const submissionSignature = JSON.stringify({
      message: trimmedMessage,
      conversationId,
      agent: submittedAgent,
      documentIds,
      files: imageFiles.map((file) => [file.name, file.size, file.lastModified]),
    })
    const retryable = retryableSubmissionRef.current?.signature === submissionSignature
      ? retryableSubmissionRef.current
      : null
    const requestId = retryable?.requestId ?? createRequestId()
    retryableSubmissionRef.current = {
      signature: submissionSignature,
      requestId,
      uploadedImages: retryable?.uploadedImages ?? [],
    }
    const controller = new AbortController()
    let resolvedConversationId = conversationId
    let accepted = false
    let connectionKey: string | null = null
    let localMessageId: string | null = null
    listenerControllerRef.current = controller
    listenerKeyRef.current = null
    setError(null)
    setPendingQuestion(null)
    setSending(true)
    setStatus('正在连接…')
    let sent = false

    try {
      const uploadedImages = retryable?.uploadedImages.length
        ? retryable.uploadedImages
        : await Promise.all(
          imageFiles.map((file) => uploadReferenceImage(file, submittedAgent)),
        )
      retryableSubmissionRef.current = {
        signature: submissionSignature,
        requestId,
        uploadedImages,
      }
      if (activeConversationRef.current === conversationId) {
        const optimisticMessageId = `local-${Date.now()}`
        localMessageId = optimisticMessageId
        setMessages((current) => [
          ...current,
          {
            id: optimisticMessageId,
            role: 'user',
            content: trimmedMessage,
            attachments: uploadedImages.map((item, index) => ({
              attachment_id: item.attachment_id,
              image_url: '',
              previewFile: imageFiles[index],
            })),
          },
        ])
      }
      const onRun = (newConversationId: string, runId: string) => {
        accepted = true
        window.dispatchEvent(new Event('nexusai:credits-changed'))
        retryableSubmissionRef.current = null
        resolvedConversationId = newConversationId
        runByConversationRef.current.set(newConversationId, runId)
        saveRunIdentity(newConversationId, runId)
        setConversations((current) => current.some(
          (item) => item.conversation_id === newConversationId,
        ) ? current : [{
          conversation_id: newConversationId,
          title: null,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
          agent: submittedAgent,
        }, ...current])
        connectionKey = `${newConversationId}:${runId}`
        liveRunKeysRef.current.add(connectionKey)
        listenerControllerRef.current = controller
        listenerKeyRef.current = connectionKey
        activeRunRef.current = runId
        if (activeConversationRef.current === conversationId) {
          activeConversationRef.current = newConversationId
          setActiveConversationId(newConversationId)
          activeAgentRef.current = submittedAgent
          setActiveAgent(submittedAgent)
        }
      }
      const streamOptions = {
        signal: controller.signal,
        onRun,
        onEventId: (eventId: string) => {
          if (resolvedConversationId) {
            const runId = runByConversationRef.current.get(resolvedConversationId)
            if (runId) saveRunCursor(resolvedConversationId, runId, eventId)
          }
        },
        onExpired: async () => {
          if (!resolvedConversationId || !runByConversationRef.current.get(resolvedConversationId)) return null
          await refreshHistory(resolvedConversationId)
          const runId = runByConversationRef.current.get(resolvedConversationId)
          if (!runId) return null
          const latest = await getConversationRunStatus(resolvedConversationId, runId)
          return latest.status === 'queued' || latest.status === 'running'
            ? latest.last_event_id
            : null
        },
      }
      const onStreamEvent = (event: AgentEvent) => {
        const runId = resolvedConversationId
          ? runByConversationRef.current.get(resolvedConversationId)
          : undefined
        if (resolvedConversationId && runId) {
          handleAgentEvent(event, resolvedConversationId, runId)
        }
      }
      if (submittedAgent === LITERATURE_READER_AGENT) {
        await streamLiteratureChat(
          {
            message: trimmedMessage,
            ...(conversationId ? { conversation_id: conversationId } : {}),
            document_ids: documentIds,
            request_id: requestId,
          },
          onStreamEvent,
          streamOptions,
        )
      } else {
        await streamChat(
          {
            message: trimmedMessage,
            ...(conversationId ? { conversation_id: conversationId } : {}),
            ...(uploadedImages.length > 0
              ? { attachment_ids: uploadedImages.map((item) => item.attachment_id) }
              : {}),
            request_id: requestId,
          },
          onStreamEvent,
          submittedAgent,
          streamOptions,
        )
      }
      if (resolvedConversationId) await finishTurn(resolvedConversationId)
      retryableSubmissionRef.current = null
      sent = true
    } catch (requestError) {
      if (controller.signal.aborted) {
        sent = true
      } else {
        if (
          !accepted
          && requestError instanceof ApiRequestError
          && requestError.code === 'INSUFFICIENT_CREDITS'
        ) {
          window.dispatchEvent(new Event('nexusai:credits-changed'))
          if (localMessageId) {
            setMessages((current) => current.filter((message) => message.id !== localMessageId))
          }
        }
        setError(getErrorMessage(requestError))
        setStatus('请求未完成')
      }
    } finally {
      if (connectionKey) liveRunKeysRef.current.delete(connectionKey)
      if (listenerControllerRef.current === controller) {
        listenerControllerRef.current = null
        listenerKeyRef.current = null
        setSending(false)
      }
      if (activeConversationRef.current === resolvedConversationId
        && activeRunRef.current && !accepted) activeRunRef.current = null
    }
    return sent
  }

  async function resumeRun(answers: Record<string, QuestionAnswer>) {
    if (!pendingQuestion || sending) return
    const pending = pendingQuestion
    const controller = new AbortController()
    const resumeSignature = JSON.stringify({ runId: pending.runId, answers })
    const retryableResume = retryableResumeRef.current?.signature === resumeSignature
      ? retryableResumeRef.current
      : null
    const requestId = retryableResume?.requestId ?? createRequestId()
    retryableResumeRef.current = { signature: resumeSignature, requestId }
    let connectionKey: string | null = null
    listenerControllerRef.current = controller
    listenerKeyRef.current = null
    setError(null)
    setSending(true)
    setStatus('正在继续处理…')
    try {
      await resumeAgentRun(
        pending.runId,
        pending.conversationId,
        answers,
        (event) => handleAgentEvent(
          event,
          pending.conversationId,
          pending.runId,
        ),
        activeAgentRef.current,
        {
          signal: controller.signal,
          onRun: (conversationId, runId) => {
            retryableResumeRef.current = null
            const key = `${conversationId}:${runId}`
            connectionKey = key
            runByConversationRef.current.set(conversationId, runId)
            saveRunIdentity(conversationId, runId)
            liveRunKeysRef.current.add(key)
            listenerKeyRef.current = key
            activeRunRef.current = runId
          },
          onEventId: (eventId) => saveRunCursor(
            pending.conversationId,
            pending.runId,
            eventId,
          ),
          onExpired: async () => {
            clearRunCursor(pending.conversationId, pending.runId)
            await refreshHistory(pending.conversationId)
            const latest = await getConversationRunStatus(pending.conversationId, pending.runId)
            return latest.status === 'queued' || latest.status === 'running'
              ? latest.last_event_id
              : null
          },
        },
        readSavedRunCursor(pending.conversationId, pending.runId),
        requestId,
      )
      await finishTurn(pending.conversationId)
      retryableResumeRef.current = null
    } catch (requestError) {
      if (!controller.signal.aborted) {
        setError(getErrorMessage(requestError))
        setStatus('恢复请求未完成')
      }
    } finally {
      if (connectionKey) liveRunKeysRef.current.delete(connectionKey)
      if (listenerControllerRef.current === controller) {
        listenerControllerRef.current = null
        listenerKeyRef.current = null
        setSending(false)
      }
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

function upsertAssistantDelta(
  messages: DisplayMessage[],
  messageId: string,
  blockId: string,
  offset: number,
  text: string,
): DisplayMessage[] {
  const existing = messages.find((message) => message.id === messageId)
  const blocks = [...(existing?.contentBlocks ?? [])]
  const index = blocks.findIndex((block) => block.id === blockId)
  const existingText = index === -1 ? '' : readString(blocks[index].text)
  const nextText = offset > existingText.length
    ? `${existingText}${text}`
    : existingText.slice(0, offset) + text + existingText.slice(offset + text.length)
  if (index === -1) blocks.push({ id: blockId, type: 'text', text: nextText })
  else blocks[index] = { ...blocks[index], text: nextText }
  return upsertAssistantBlocks(messages, messageId, blocks, true)
}

function upsertAssistantSnapshot(
  messages: DisplayMessage[],
  messageId: string,
  blocks: DisplayContentBlock[],
  agent: AgentType,
): DisplayMessage[] {
  const existing = messages.find((message) => message.id === messageId)
  const taskResults = blocks
    .filter((block) => block.type === 'task_result')
    .map((block) => readTaskResult(block, agent))
    .filter((result): result is TaskResultSummary => result !== null)
  return upsertAssistantBlocks(
    messages,
    messageId,
    blocks,
    existing?.streaming ?? false,
    taskResults,
  )
}

function upsertAssistantBlocks(
  messages: DisplayMessage[],
  messageId: string,
  blocks: DisplayContentBlock[],
  streaming: boolean,
  taskResults?: TaskResultSummary[],
): DisplayMessage[] {
  const text = blocks
    .filter((block) => block.type === 'text' && typeof block.text === 'string')
    .map((block) => block.text)
    .join('\n')
  const question = blocks.find((block) => block.type === 'question' && Array.isArray(block.questions))
  const message: DisplayMessage = {
    ...(messages.find((item) => item.id === messageId) ?? {}),
    id: messageId,
    role: 'assistant',
    content: text,
    contentBlocks: blocks,
    taskResults: taskResults ?? messages.find((item) => item.id === messageId)?.taskResults ?? [],
    streaming,
    ...(question && Array.isArray(question.questions)
      ? {
          questionBatch: {
            runId: readString(question.run_id),
            questionRound: readInteger(question.question_round) ?? 1,
            maxQuestionRounds: readInteger(question.max_question_rounds)
              ?? MAX_QUESTION_ROUNDS_PER_RUN,
            questions: question.questions as Question[],
          },
        }
      : {}),
  }
  const index = messages.findIndex((item) => item.id === messageId)
  if (index === -1) return [...messages, message]
  return messages.map((item, itemIndex) => itemIndex === index ? message : item)
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

function getErrorMessage(error: unknown): string {
  return error instanceof Error ? error.message : '发生未知错误，请稍后重试。'
}

function createRequestId(): string {
  return globalThis.crypto?.randomUUID?.()
    ?? `${Date.now().toString(36)}_${Math.random().toString(36).slice(2).padEnd(16, '0')}`
}

function runIdentityKey(conversationId: string): string {
  return `nexusai:agent-run:${conversationId}`
}

function runCursorKey(conversationId: string, runId: string): string {
  return `nexusai:agent-cursor:v2:${conversationId}:${runId}`
}

function saveRunIdentity(conversationId: string, runId: string): void {
  try {
    window.sessionStorage.setItem(runIdentityKey(conversationId), runId)
  } catch {
    // 隐私模式禁用 sessionStorage 时仍可在当前连接内续接。
  }
}

function readSavedRunCursor(conversationId: string, runId: string): string | null {
  try {
    if (window.sessionStorage.getItem(runIdentityKey(conversationId)) !== runId) return null
    return window.sessionStorage.getItem(runCursorKey(conversationId, runId))
  } catch {
    return null
  }
}

function saveRunCursor(conversationId: string, runId: string, eventId: string): void {
  try {
    saveRunIdentity(conversationId, runId)
    window.sessionStorage.setItem(runCursorKey(conversationId, runId), eventId)
  } catch {
    // 游标不可持久化时，服务端仍可从历史和运行状态恢复。
  }
}

function clearRunCursor(conversationId: string, runId: string): void {
  try {
    window.sessionStorage.removeItem(runCursorKey(conversationId, runId))
  } catch {
    // 存储不可用不影响历史消息恢复。
  }
}
