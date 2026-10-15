import { useState } from 'react'
import { getApiDocsUrl } from '../../shared/api/http'
import AgentInteractionCard from './components/AgentInteractionCard'
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
  const chat = useChatSession()

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
    const sent = await chat.sendMessage(message, pendingImages)
    if (sent) {
      setDraft('')
      setPendingImages([])
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
        onCreate={() => {
          setPendingImages([])
          setAttachmentError(null)
          chat.createConversation()
        }}
        onSelect={(conversationId) => {
          setPendingImages([])
          setAttachmentError(null)
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
              <span><i className="status-dot" /> {chat.status}</span>
            </div>
          </div>
          <a href={getApiDocsUrl()} target="_blank" rel="noreferrer" className="docs-link">API 文档 ↗</a>
          <button className="mobile-new-conversation" type="button" onClick={chat.createConversation} disabled={chat.sending}>＋ 新对话</button>
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
              questions={chat.pendingQuestion.questions}
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
          disabled={chat.sending || Boolean(chat.pendingQuestion)}
          onChange={setDraft}
          onSend={() => { void handleSend() }}
          onCancel={() => { void chat.cancelRun() }}
          canCancel={chat.canCancel}
          agents={chat.agents}
          activeAgentId={chat.activeAgentId}
          onSelectAgent={(agentId) => {
            setPendingImages([])
            setAttachmentError(null)
            chat.selectAgent(agentId)
          }}
          supportsImageUpload={chat.agents.find((agent) => agent.agent_id === chat.activeAgentId)?.supports_image_upload ?? false}
          attachments={pendingImages}
          onAddAttachments={addAttachments}
          onRemoveAttachment={(index) => setPendingImages((current) => current.filter((_, itemIndex) => itemIndex !== index))}
        />
      </section>
    </main>
  )
}

export default ChatPage
