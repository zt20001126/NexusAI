import { useEffect, useState } from 'react'
import { getApiDocsUrl } from '../../shared/api/http'
import AgentInteractionCard from './components/AgentInteractionCard'
import AgentSelectionDialog from './components/AgentSelectionDialog'
import Composer from './components/Composer'
import ConversationSidebar from './components/ConversationSidebar'
import MessageList from './components/MessageList'
import {
  LISTING_AGENT_ID,
  MAX_REFERENCE_IMAGE_BYTES,
  MAX_REFERENCE_IMAGES,
} from './constants'
import { useChatSession } from './hooks/useChatSession'

/** 组合聊天页面的导航、消息流、追问卡片和输入框。 */
function ChatPage() {
  const [draft, setDraft] = useState('')
  const [pendingImages, setPendingImages] = useState<File[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [agentSelectionOpen, setAgentSelectionOpen] = useState(false)
  const [newConversationReady, setNewConversationReady] = useState(false)
  const chat = useChatSession()
  useEffect(() => {
    if (!chat.sidebarLoading && !chat.activeConversationId && !newConversationReady) {
      setAgentSelectionOpen(true)
    }
  }, [chat.activeConversationId, chat.sidebarLoading, newConversationReady])

  function openAgentSelection() {
    setAgentSelectionOpen(true)
  }

  function selectAgent(agentId: string) {
    setDraft('')
    setPendingImages([])
    setAttachmentError(null)
    chat.selectAgent(agentId)
    setNewConversationReady(true)
    setAgentSelectionOpen(false)
  }

  function cancelAgentSelection() {
    setAgentSelectionOpen(false)
  }

  const pendingQuestionKey = chat.pendingQuestion
    ? JSON.stringify({
        runId: chat.pendingQuestion.runId,
        questionRound: chat.pendingQuestion.questionRound,
        questions: chat.pendingQuestion.questions.map(({ id, title, prompt }) => [id, title, prompt]),
      })
    : undefined
  const activeAgentName = chat.agents.find((agent) => agent.agent_id === chat.activeAgentId)?.name
    || (chat.agentsLoading ? '智能体加载中' : '智能体不可用')

  async function handleSend() {
    const message = draft.trim()
      || (chat.activeAgentId === LISTING_AGENT_ID && pendingImages.length > 0
        ? '请根据已上传的商品图片生成淘宝 Listing。'
        : '')
    if (!message || chat.sending) return
    if (chat.activeAgentId === LISTING_AGENT_ID && pendingImages.length === 0) {
      setAttachmentError('Listing 生成需要至少上传一张商品图片。')
      return
    }
    setAttachmentError(null)
    const submittedDraft = draft
    const submittedImages = pendingImages
    setDraft('')
    setPendingImages([])

    const sent = await chat.sendMessage(message, submittedImages)
    if (!sent) {
      setDraft((current) => current || submittedDraft)
      setPendingImages((current) => current.length > 0 ? current : submittedImages)
    }
  }

  function addAttachments(files: File[]) {
    setAttachmentError(null)
    const valid = files.filter((file) =>
      (file.type === 'image/png' || file.type === 'image/jpeg')
      && file.size > 0
      && file.size <= MAX_REFERENCE_IMAGE_BYTES,
    )
    if (valid.length !== files.length) {
      setAttachmentError('仅支持不超过 5 MiB 的 PNG/JPEG 图片。')
    }
    const remaining = Math.max(0, MAX_REFERENCE_IMAGES - pendingImages.length)
    if (valid.length > remaining) setAttachmentError('参考图片最多添加 3 张。')
    setPendingImages((current) => [...current, ...valid.slice(0, remaining)])
  }

  return (
    <main className="chat-app-shell">
      <ConversationSidebar
        conversations={chat.conversations}
        activeConversationId={chat.activeConversationId}
        loading={chat.sidebarLoading}
        hasMore={chat.conversationHasMore}
        loadingMore={chat.loadingMoreConversations}
        disabled={chat.sending}
        error={chat.sidebarError}
        onCreate={openAgentSelection}
        onSelect={(conversationId) => {
          setPendingImages([])
          setAttachmentError(null)
          setNewConversationReady(false)
          setAgentSelectionOpen(false)
          chat.selectConversation(conversationId)
        }}
        onLoadMore={() => { void chat.loadMoreConversations() }}
        onRetry={() => { void chat.refreshConversations() }}
      />

      <section className="chat-main">
        <header className="chat-topbar">
          <div className="topbar-title">
            <img className="mobile-brand-mark" src="/brand/nexusai-icon.png" alt="" />
            <div>
              <strong>{chat.activeConversation?.title || (chat.activeConversationId ? '会话' : '新对话')}</strong>
              <span><i className="status-dot" /> {activeAgentName} · {chat.status}</span>
            </div>
          </div>
          <a href={getApiDocsUrl()} target="_blank" rel="noreferrer" className="docs-link">API 文档 ↗</a>
          <button className="mobile-new-conversation" type="button" onClick={openAgentSelection} disabled={chat.sending}>＋ 新对话</button>
        </header>

        <div className="chat-content">
          {chat.olderCursor !== null && !chat.historyLoading && (
            <button className="load-older-button" type="button" onClick={() => { void chat.loadOlderMessages() }} disabled={chat.loadingOlder}>
              {chat.loadingOlder ? '正在加载…' : '↑ 查看更早消息'}
            </button>
          )}
          <MessageList
            messages={chat.messages}
            loading={chat.historyLoading}
            conversationId={chat.activeConversationId}
          />
          {chat.pendingQuestion && chat.pendingQuestion.questions.length > 0 && (
            <AgentInteractionCard
              key={pendingQuestionKey}
              questions={chat.pendingQuestion.questions}
              questionRound={chat.pendingQuestion.questionRound}
              maxQuestionRounds={chat.pendingQuestion.maxQuestionRounds}
              disabled={chat.sending}
              onSubmit={(answers) => { void chat.resumeRun(answers) }}
            />
          )}
          {(chat.error || attachmentError) && (
            <div className="error-banner" role="alert">{attachmentError || chat.error}</div>
          )}
        </div>

        <Composer
          value={draft}
          disabled={chat.sending || Boolean(chat.pendingQuestion) || agentSelectionOpen || (!chat.activeConversationId && !newConversationReady)}
          onChange={setDraft}
          onSend={() => { void handleSend() }}
          onCancel={() => { void chat.cancelRun() }}
          canCancel={chat.canCancel}
          supportsImageUpload={chat.agents.find((agent) => agent.agent_id === chat.activeAgentId)?.supports_image_upload ?? false}
          attachments={pendingImages}
          onAddAttachments={addAttachments}
          onRemoveAttachment={(index) => setPendingImages((current) => current.filter((_, itemIndex) => itemIndex !== index))}
        />
      </section>
      <AgentSelectionDialog
        open={agentSelectionOpen}
        canCancel={Boolean(chat.activeConversationId) || newConversationReady}
        agents={chat.agents}
        agentsLoading={chat.agentsLoading}
        agentsError={chat.agentsError}
        onSelect={selectAgent}
        onCancel={cancelAgentSelection}
        onRetry={() => { void chat.loadAgents() }}
      />
    </main>
  )
}

export default ChatPage
