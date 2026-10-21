import { useEffect, useRef, useState, type KeyboardEvent } from 'react'
import { JOB_AGENT } from '../constants'
import { useChatSession } from '../hooks/useChatSession'
import Composer from './Composer'
import MessageList from './MessageList'

/** 在简历工作台右栏展示求职智能体，沿用聊天功能的会话与流式运行协议。 */
function JobChatPanel() {
  const chat = useChatSession()
  const initialized = useRef(false)
  const [draft, setDraft] = useState('')
  const [historyOpen, setHistoryOpen] = useState(false)
  const [highlightedHistoryIndex, setHighlightedHistoryIndex] = useState(0)
  const historyRef = useRef<HTMLDivElement>(null)
  const historyTriggerRef = useRef<HTMLButtonElement>(null)
  const historyOptionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const jobConversations = chat.conversations.filter((item) => item.agent === JOB_AGENT)
  const activeConversation = jobConversations.find((item) => item.conversation_id === chat.activeConversationId)

  useEffect(() => {
    if (!historyOpen) return
    function closeOnOutsidePointer(event: PointerEvent) {
      if (event.target instanceof Node && !historyRef.current?.contains(event.target)) setHistoryOpen(false)
    }
    document.addEventListener('pointerdown', closeOnOutsidePointer)
    return () => document.removeEventListener('pointerdown', closeOnOutsidePointer)
  }, [historyOpen])

  function handleHistoryKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === 'Escape') {
      event.preventDefault()
      setHistoryOpen(false)
      historyTriggerRef.current?.focus()
      return
    }
    if (jobConversations.length === 0) return
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      const direction = event.key === 'ArrowDown' ? 1 : -1
      const nextIndex = historyOpen
        ? (highlightedHistoryIndex + direction + jobConversations.length) % jobConversations.length
        : jobConversations.findIndex((item) => item.conversation_id === chat.activeConversationId) >= 0
          ? jobConversations.findIndex((item) => item.conversation_id === chat.activeConversationId)
          : 0
      setHighlightedHistoryIndex(nextIndex)
      setHistoryOpen(true)
      requestAnimationFrame(() => historyOptionRefs.current[nextIndex]?.focus())
    }
  }

  useEffect(() => {
    if (chat.sidebarLoading || initialized.current) return
    initialized.current = true
    const latest = chat.conversations.find((item) => item.agent === JOB_AGENT)
    if (latest) chat.selectConversation(latest.conversation_id)
    else chat.selectAgent(JOB_AGENT)
  }, [chat.sidebarLoading, chat.conversations, chat.selectAgent, chat.selectConversation])

  async function send() {
    const message = draft.trim()
    if (!message || chat.sending) return
    setDraft('')
    const sent = await chat.sendMessage(message)
    if (!sent) setDraft((current) => current || message)
  }

  return (
    <section className="resume-job-panel" aria-label="求职助手对话">
      <header className="resume-job-header">
        <div><p className="resume-editor-eyebrow">JOB ASSISTANT</p><h2>求职助手</h2></div>
        <button type="button" className="resume-secondary-button" disabled={!initialized.current || chat.sending} onClick={() => { chat.selectAgent(JOB_AGENT); setDraft('') }}>新对话</button>
      </header>
      <div className="resume-job-history" ref={historyRef} onKeyDown={handleHistoryKeyDown}>
        <span className="resume-job-history-label">历史对话</span>
        <div className="resume-job-history-control">
          <button
            type="button"
            className={`resume-job-history-trigger${historyOpen ? ' is-open' : ''}`}
            ref={historyTriggerRef}
            aria-haspopup="listbox"
            aria-expanded={historyOpen}
            aria-label={`历史对话：${activeConversation?.title || (chat.activeConversationId ? '未命名对话' : '当前为新对话')}`}
            disabled={chat.sending}
            onClick={() => setHistoryOpen((open) => !open)}
          >
            <span className="resume-job-history-value">{activeConversation?.title || (chat.activeConversationId ? '未命名对话' : '当前为新对话')}</span>
            <span className="resume-job-history-chevron" aria-hidden="true">⌄</span>
          </button>
          <div className={`resume-job-history-menu${historyOpen ? ' is-open' : ''}`} role="listbox" aria-label="历史对话列表" aria-hidden={!historyOpen}>
            {jobConversations.length > 0 ? jobConversations.map((item, index) => {
              const selected = item.conversation_id === chat.activeConversationId
              return (
                <button
                  type="button"
                  role="option"
                  aria-selected={selected}
                  className={`resume-job-history-option${selected ? ' is-selected' : ''}`}
                  key={item.conversation_id}
                  ref={(element) => { historyOptionRefs.current[index] = element }}
                  tabIndex={historyOpen && highlightedHistoryIndex === index ? 0 : -1}
                  onFocus={() => setHighlightedHistoryIndex(index)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      chat.selectConversation(item.conversation_id)
                      setHistoryOpen(false)
                    } else if (event.key === 'Home' || event.key === 'End') {
                      event.preventDefault()
                      const nextIndex = event.key === 'Home' ? 0 : jobConversations.length - 1
                      setHighlightedHistoryIndex(nextIndex)
                      historyOptionRefs.current[nextIndex]?.focus()
                    }
                  }}
                  onClick={() => { chat.selectConversation(item.conversation_id); setHistoryOpen(false) }}
                >
                  <span>{item.title || '未命名对话'}</span>
                  {selected && <span className="resume-job-history-check" aria-hidden="true">✓</span>}
                </button>
              )
            }) : <p className="resume-job-history-empty">暂无历史对话，开始交流后会显示在这里。</p>}
          </div>
        </div>
      </div>
      {chat.sidebarLoading && <p className="resume-job-state" role="status">正在加载对话…</p>}
      {chat.sidebarError && <p className="resume-job-error" role="alert">{chat.sidebarError} <button type="button" onClick={() => { void chat.refreshConversations() }}>重试</button></p>}
      <div className="resume-job-messages">
        <MessageList
          messages={chat.messages}
          loading={chat.historyLoading}
          conversationId={chat.activeConversationId}
          agent={JOB_AGENT}
          pendingQuestion={chat.pendingQuestion}
          questionDisabled={chat.sending}
          onSubmitQuestion={(answers) => { void chat.resumeRun(answers) }}
        />
      </div>
      {chat.olderCursor && !chat.historyLoading && <button className="resume-job-older" type="button" disabled={chat.loadingOlder} onClick={() => { void chat.loadOlderMessages() }}>{chat.loadingOlder ? '正在加载…' : '查看更早消息'}</button>}
      {chat.error && <p className="resume-job-error" role="alert">{chat.error}</p>}
      <Composer
        value={draft}
        disabled={!initialized.current || Boolean(chat.pendingQuestion)}
        sending={chat.sending}
        onChange={setDraft}
        onSend={() => { void send() }}
        onCancel={() => { void chat.cancelRun() }}
        canCancel={chat.canCancel}
        supportsImageUpload={false}
        attachments={[]}
        onAddAttachments={() => {}}
        onRemoveAttachment={() => {}}
      />
    </section>
  )
}

export default JobChatPanel
