import { useLayoutEffect, useRef } from 'react'
import type { ConversationMessage } from '../api/conversations'

export interface DisplayMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
  streaming?: boolean
  createdAt?: string
}

interface MessageListProps {
  messages: DisplayMessage[]
  loading: boolean
  conversationId: string | null
}

/** 展示历史消息、当前流式回复和首次进入页面的引导内容。 */
function MessageList({ messages, loading, conversationId }: MessageListProps) {
  const bottomRef = useRef<HTMLDivElement>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const previousHeight = useRef(0)
  const previousFirstMessageId = useRef<string | null>(null)

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const firstMessageId = messages[0]?.id ?? null
    const previousIndex = previousFirstMessageId.current
      ? messages.findIndex((message) => message.id === previousFirstMessageId.current)
      : -1

    if (previousIndex > 0) {
      list.scrollTop += list.scrollHeight - previousHeight.current
    } else if (previousIndex === -1 || list.scrollHeight - list.scrollTop - list.clientHeight < 120) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
    }

    previousHeight.current = list.scrollHeight
    previousFirstMessageId.current = firstMessageId
  }, [messages])

  if (loading) {
    return <div className="message-scroll-area"><div className="message-state">正在读取这段对话…</div></div>
  }

  if (messages.length === 0) {
    return (
      <div className="message-scroll-area" ref={listRef}>
      <div className="welcome-panel">
        <div className="welcome-orbit" aria-hidden="true"><span>✳</span></div>
        <p className="eyebrow">NEXUSAI ASSISTANT</p>
        <h1>{conversationId ? '继续这段对话' : '你好，今天想一起完成什么？'}</h1>
        <p>描述你的目标或问题，NexusAI 会和你一起梳理下一步。</p>
        <div className="suggestion-row">
          <span>整理一个开发目标</span>
          <span>梳理业务流程</span>
          <span>从一个问题开始</span>
        </div>
      </div>
      </div>
    )
  }

  return (
    <div className="message-scroll-area" ref={listRef}>
    <div className="message-list" aria-live="polite">
      {messages.map((message) => (
        <article className={`message-row ${message.role}`} key={message.id}>
          {message.role === 'assistant' && <div className="assistant-avatar" aria-hidden="true">N</div>}
          <div className="message-column">
            <div className="message-author">{message.role === 'user' ? '你' : 'NexusAI'}</div>
            <div className={`message-bubble ${message.role}`}>
              {message.content ? <span>{message.content}</span> : <span className="typing-dots">正在思考…</span>}
              {message.streaming && <span className="stream-caret" aria-hidden="true" />}
            </div>
          </div>
          {message.role === 'user' && <div className="user-avatar" aria-hidden="true">我</div>}
        </article>
      ))}
      <div ref={bottomRef} />
    </div>
    </div>
  )
}

export function toDisplayMessage(message: ConversationMessage): DisplayMessage {
  return {
    id: message.message_id,
    role: message.role,
    content: message.content,
    createdAt: message.created_at,
  }
}

export default MessageList
