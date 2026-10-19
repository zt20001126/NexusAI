import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { Question, QuestionAnswer, QuestionOptionValue } from '../api/agent'
import type { DisplayAttachment, DisplayMessage, DisplayQuestionBatch } from '../model/messages'
import type { AgentType } from '../constants'
import AgentAvatar from './AgentAvatar'
import AgentInteractionCard from './AgentInteractionCard'
import ListingResultCard from './ListingResultCard'
import ResearchResultCard from './ResearchResultCard'

const AUTO_SCROLL_THRESHOLD_PX = 120

interface PendingQuestionView {
  runId: string
  questions: Question[]
  questionRound: number
  maxQuestionRounds: number
}

interface MessageListProps {
  messages: DisplayMessage[]
  loading: boolean
  conversationId: string | null
  agent: AgentType
  pendingQuestion: PendingQuestionView | null
  questionDisabled: boolean
  onSubmitQuestion: (answers: Record<string, QuestionAnswer>) => void
}

/** 展示历史消息、当前流式回复和首次进入页面的引导内容。 */
function MessageList({
  messages,
  loading,
  conversationId,
  agent,
  pendingQuestion,
  questionDisabled,
  onSubmitQuestion,
}: MessageListProps) {
  const listRef = useRef<HTMLDivElement>(null)
  const previousHeight = useRef(0)
  const previousFirstMessageId = useRef<string | null>(null)
  const previousLastMessageId = useRef<string | null>(null)
  const shouldStickToBottom = useRef(true)
  const visibleMessages = useMemo(() => {
    const currentQuestion = pendingQuestion
    if (!currentQuestion || currentQuestion.questions.length === 0) return messages
    const hasQuestionMessage = messages.some((message) => (
      message.questionBatch?.runId === currentQuestion.runId
      && message.questionBatch.questionRound === currentQuestion.questionRound
    ))
    if (hasQuestionMessage) return messages

    return [
      ...messages,
      {
        id: `pending-question-${currentQuestion.runId}-${currentQuestion.questionRound}`,
        role: 'assistant' as const,
        content: '',
        questionBatch: {
          runId: currentQuestion.runId,
          questionRound: currentQuestion.questionRound,
          maxQuestionRounds: currentQuestion.maxQuestionRounds,
          questions: currentQuestion.questions,
        },
      } satisfies DisplayMessage,
    ]
  }, [messages, pendingQuestion])

  useLayoutEffect(() => {
    const list = listRef.current
    if (!list) return
    const firstMessageId = visibleMessages[0]?.id ?? null
    const lastMessageId = visibleMessages[visibleMessages.length - 1]?.id ?? null
    const previousIndex = previousFirstMessageId.current
      ? visibleMessages.findIndex((message) => message.id === previousFirstMessageId.current)
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
  }, [visibleMessages])

  function handleScroll() {
    const list = listRef.current
    if (!list) return
    const distanceFromBottom = list.scrollHeight - list.scrollTop - list.clientHeight
    shouldStickToBottom.current = distanceFromBottom <= AUTO_SCROLL_THRESHOLD_PX
  }

  if (loading && !pendingQuestion) {
    return <div className="message-scroll-area"><div className="message-state">正在读取这段对话…</div></div>
  }

  if (visibleMessages.length === 0) {
    return (
      <div className="message-scroll-area" ref={listRef} onScroll={handleScroll}>
      <div className="welcome-panel">
        <div className="welcome-orbit" aria-hidden="true">
          <AgentAvatar agent={agent} />
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
      {visibleMessages.map((message) => {
        const questionBatch = message.questionBatch
        const isQuestionActive = questionBatch
          && pendingQuestion?.runId === questionBatch.runId
          && pendingQuestion.questionRound === questionBatch.questionRound
        const messageKey = questionBatch
          ? `question-${questionBatch.runId}-${questionBatch.questionRound}`
          : message.id

        return (
        <article className={`message-row ${message.role}`} key={messageKey}>
          {message.role === 'assistant' && (
            <div className="assistant-avatar" aria-hidden="true">
              <AgentAvatar agent={agent} />
            </div>
          )}
          <div className="message-column">
            {questionBatch ? (
              <>
                {isQuestionActive ? (
                  <AgentInteractionCard
                    key={`${questionBatch.runId}-${questionBatch.questionRound}`}
                    questions={questionBatch.questions}
                    questionRound={questionBatch.questionRound}
                    maxQuestionRounds={questionBatch.maxQuestionRounds}
                    disabled={questionDisabled}
                    embedded
                    onSubmit={onSubmitQuestion}
                  />
                ) : (
                  <QuestionBatchHistoryCard questionBatch={questionBatch} />
                )}
                <TaskResultCards results={message.taskResults} />
              </>
            ) : (
              <div className={`message-bubble ${message.role}${message.questionAnswers?.length ? ' question-answer-bubble' : ''}`}>
                {message.content && !message.questionAnswers?.length && (
                  message.role === 'assistant'
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
                )}
                {!message.content
                  && !message.questionAnswers?.length
                  && !message.taskResults?.length
                  && !message.attachments?.length
                  && <span className="typing-dots">正在思考…</span>}
                {message.questionAnswers && message.questionAnswers.length > 0 && (
                  <section className="message-question-answers" aria-label="已提交的补充回答">
                    <header className="message-question-answers-heading">
                      <span>已补充信息</span>
                      <span className="message-question-answers-count">
                        {message.questionAnswers.length} 项
                      </span>
                    </header>
                    <dl className="message-question-answer-list">
                      {message.questionAnswers.map((answer) => (
                        <div className="message-question-answer" key={answer.questionId}>
                          <dt>{answer.title}</dt>
                          <dd>
                            {answer.values.map((value, index) => (
                              <span className="message-question-answer-value" key={`${value}-${index}`}>
                                {value}
                              </span>
                            ))}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                )}
                {message.role === 'user' && (message.attachments?.length ?? 0) > 0 && (
                  <div className="message-attachments" aria-label="已发送图片">
                    {message.attachments?.map((attachment) => (
                      <MessageImage key={attachment.attachment_id} attachment={attachment} />
                    ))}
                  </div>
                )}
                <TaskResultCards results={message.taskResults} />
                {message.streaming && <span className="stream-caret" aria-hidden="true" />}
              </div>
            )}
          </div>
          {message.role === 'user' && (
            <div className="user-avatar" aria-hidden="true">
              <img src="/avatars/user.png" alt="" />
            </div>
          )}
        </article>
        )
      })}
    </div>
    </div>
  )
}

function QuestionBatchHistoryCard({ questionBatch }: { questionBatch: DisplayQuestionBatch }) {
  return (
    <section className="interaction-card interaction-card-message question-batch-history">
      <header className="interaction-heading">
        <div>
          <strong>模型提出的问题</strong>
          <p>本轮需要确认 {questionBatch.questions.length} 项信息。</p>
        </div>
        <span className="interaction-round-badge">
          第 {questionBatch.questionRound} / {questionBatch.maxQuestionRounds} 轮
        </span>
      </header>
      <div className="interaction-questions">
        {questionBatch.questions.map((question, index) => (
          <fieldset className="interaction-field question-history-field" key={question.id}>
            <legend>
              <span className="interaction-question-index">
                问题 {index + 1} / {questionBatch.questions.length}
              </span>
              <span className="interaction-question-title">{question.title}</span>
            </legend>
            {question.prompt && <p className="interaction-prompt">{question.prompt}</p>}
            <QuestionHistoryOptions question={question} />
          </fieldset>
        ))}
      </div>
    </section>
  )
}

function QuestionHistoryOptions({ question }: { question: Question }) {
  const options: QuestionOptionValue[] = question.type === 'SingleChoice'
    || question.type === 'MultiChoice'
    ? question.options
    : question.type === 'Confirmation'
      ? ['确认', '取消']
      : []
  if (options.length === 0) return null

  return (
    <ul className="question-history-options">
      {options.map((option) => {
        const label = typeof option === 'string' ? option : option.label
        const description = typeof option === 'string' ? undefined : option.description
        return (
          <li key={label}>
            <span>{label}</span>
            {description && <small>{description}</small>}
          </li>
        )
      })}
    </ul>
  )
}

function TaskResultCards({ results }: { results: DisplayMessage['taskResults'] }) {
  if (!results?.length) return null
  return (
    <>
      {results.map((result) => (
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
    </>
  )
}

function MessageImage({ attachment }: { attachment: DisplayAttachment }) {
  const [previewUrl, setPreviewUrl] = useState('')

  useEffect(() => {
    if (!attachment.previewFile) return
    const url = URL.createObjectURL(attachment.previewFile)
    setPreviewUrl(url)
    return () => URL.revokeObjectURL(url)
  }, [attachment.previewFile])

  const imageUrl = attachment.image_url || previewUrl
  if (!imageUrl) return null
  return (
    <a href={imageUrl} target="_blank" rel="noreferrer" aria-label="查看上传的图片">
      <img src={imageUrl} alt="用户上传的图片" loading="lazy" />
    </a>
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
