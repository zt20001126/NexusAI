import { useLayoutEffect, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { DisplayMessage } from '../model/messages'
import ListingResultCard from './ListingResultCard'
import ResearchResultCard from './ResearchResultCard'

const AUTO_SCROLL_THRESHOLD_PX = 120

interface MessageListProps {
  messages: DisplayMessage[]
  loading: boolean
  conversationId: string | null
}

/** 展示历史消息、当前流式回复和首次进入页面的引导内容。 */
function MessageList({ messages, loading, conversationId }: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const previousHeight = useRef(0)
  const previousFirstMessageId = useRef<string | null>(null)
  const previousLastMessageId = useRef<string | null>(null)
  const shouldStickToBottom = useRef(true)

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const firstMessageId = messages[0]?.id ?? null
    const lastMessageId = messages[messages.length - 1]?.id ?? null
    const previousIndex = previousFirstMessageId.current
      ? messages.findIndex((message) => message.id === previousFirstMessageId.current)
      : -1

    if (previousIndex > 0) {
      list.scrollTop += list.scrollHeight - previousHeight.current
    } else {
      if (lastMessageId && lastMessageId !== previousLastMessageId.current) {
        shouldStickToBottom.current = true
      }
      if (shouldStickToBottom.current) {
        list.scrollTop = list.scrollHeight
      }
    }

    previousHeight.current = list.scrollHeight
    previousFirstMessageId.current = firstMessageId
    previousLastMessageId.current = lastMessageId
  }, [messages])

  function handleScroll() {
    const list = listRef.current
    if (!list) return
    const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    shouldStickToBottom.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX
  }

  if (loading) {
    return <div className="message-scroll-area"><div className="message-state">正在读取这段对话…</div></div>
  }

  if (messages.length === 0) {
    return (
      <div className="message-scroll-area" ref={listRef} onScroll={handleScroll}>
      <div className="welcome-panel">
        <div className="welcome-orbit" aria-hidden="true">
          <img src="/brand/nexusai-icon.png" alt="" />
        </div>
        <p className="eyebrow">NEXUSAI ASSISTANT</p>
        <h1>{conversationId ? '继续这段对话' : '你好，今天想一起完成什么？'}</h1>
        <p>描述你的目标或问题，NexusAI 会和你一起梳理下一步。</p>
      </div>
      </div>
    )
  }

  return (
    <div className="message-scroll-area" ref={listRef} onScroll={handleScroll}>
    <div className="message-list" aria-live="polite">
      {messages.map((message) => (
        <article className={`message-row ${message.role}`} key={message.id}>
          {message.role === 'assistant' && (
            <div className="assistant-avatar" aria-hidden="true">
              <img src="/brand/nexusai-icon.png" alt="" />
            </div>
          )}
          <div className="message-column">
            <div className="message-author">{message.role === 'user' ? '当前用户' : 'NexusAI'}</div>
            <div className={`message-bubble ${message.role}`}>
              {message.content
                ? message.role === 'assistant'
                  ? (
                    <div className="message-markdown">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ href, children }) => (
                            <a href={href} target="_blank" rel="noreferrer">
                              {children}
                            </a>
                          ),
                        }}
                      >
                        {message.content}
                      </ReactMarkdown>
                    </div>
                  )
                  : <span>{message.content}</span>
                : message.taskResults?.length
                  ? null
                  : <span className="typing-dots">正在思考…</span>}
              {message.taskResults?.map((result) => (
                <div className="task-result-card" key={result.task_result_id}>
                  {result.result_type === 'listing' ? (
                    <ListingResultCard result={result} />
                  ) : result.result_type === 'research_search' ? (
                    <ResearchResultCard result={result} />
                  ) : result.generation_status === 'succeeded' && result.image_url ? (
                    <a href={result.image_url} target="_blank" rel="noreferrer">
                      <img src={result.image_url} alt="生成的淘宝商品图片" loading="lazy" />
                    </a>
                  ) : result.generation_status === 'failed' ? (
                    <p role="status">图片生成失败：{result.error_message || '请调整描述后重试。'}</p>
                  ) : (
                    <p role="status">{taskResultStatusText(result.generation_status)}</p>
                  )}
                </div>
              ))}
              {message.streaming && <span className="stream-caret" aria-hidden="true" />}
            </div>
          </div>
          {message.role === 'user' && (
            <div className="user-avatar" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false">
                <circle cx="12" cy="8" r="3.25" />
                <path d="M5.5 19a6.5 6.5 0 0 1 13 0" />
              </svg>
            </div>
          )}
        </article>
      ))}
    </div>
    </div>
  )
}

function taskResultStatusText(status: string): string {
  switch (status) {
    case 'pending': return '图片任务已创建…'
    case 'awaiting_input': return '等待图片参数…'
    case 'running': return '正在生成图片…'
    case 'cancelled': return '图片生成已取消。'
    default: return '正在准备图片结果…'
  }
}

export default MessageList
