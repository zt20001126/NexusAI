import { lazy, Suspense, useEffect, useState } from 'react'
import AgentDirectory from './components/AgentDirectory'
import AgentInteractionCard from './components/AgentInteractionCard'
import AgentSelectionDialog from './components/AgentSelectionDialog'
import Composer from './components/Composer'
import ConversationSidebar from './components/ConversationSidebar'
import LiteratureLibraryPanel from './components/LiteratureLibraryPanel'
import MessageList from './components/MessageList'
import {
  COMMON_AGENT_ID,
  LITERATURE_READER_AGENT_ID,
  LISTING_AGENT_ID,
  MAX_REFERENCE_IMAGE_BYTES,
  MAX_REFERENCE_IMAGES,
} from './constants'
import { useChatSession } from './hooks/useChatSession'

const DinoRunPage = lazy(() => import('../dino-run/DinoRunPage'))

type MainView = 'directory' | 'game' | 'workspace'

/** 组合聊天页面的导航、消息流、追问卡片和输入框。 */
function ChatPage() {
  const [draft, setDraft] = useState('')
  const [pendingImages, setPendingImages] = useState<File[]>([])
  const [selectedDocumentIds, setSelectedDocumentIds] = useState<string[]>([])
  const [attachmentError, setAttachmentError] = useState<string | null>(null)
  const [agentSelectionOpen, setAgentSelectionOpen] = useState(false)
  const [mainView, setMainView] = useState<MainView>('directory')
  const agentDirectoryOpen = mainView === 'directory'
  const [newConversationReady, setNewConversationReady] = useState(false)
  const chat = useChatSession()
  useEffect(() => {
    if (mainView === 'workspace' && !chat.sidebarLoading && !chat.activeConversationId && !newConversationReady) {
      setAgentSelectionOpen(true)
    }
  }, [mainView, chat.activeConversationId, chat.sidebarLoading, newConversationReady])

  function openAgentSelection() {
    setAgentSelectionOpen(true)
  }

  function openAgentDirectory() {
    setAgentSelectionOpen(false)
    setMainView('directory')
  }

  function openGame() {
    setAgentSelectionOpen(false)
    setMainView('game')
  }

  function selectAgent(agentId: string) {
    setDraft('')
    setPendingImages([])
    setSelectedDocumentIds([])
    setAttachmentError(null)
    chat.selectAgent(agentId)
    setNewConversationReady(true)
    setAgentSelectionOpen(false)
    setMainView('workspace')
  }

  function cancelAgentSelection() {
    setAgentSelectionOpen(false)
  }

  const pendingQuestionKey = chat.pendingQuestion
    ? JSON.stringify({
        runId: chat.pendingQuestion.runId,
        questionRound: chat.pendingQuestion.questionRound,
        questions: chat.pendingQuestion.questions,
      })
    : undefined
  const latestAssistantResponseId = [...chat.messages].reverse().find((message) =>
    message.role === 'assistant'
    && (message.content.trim().length > 0 || (message.taskResults?.length ?? 0) > 0),
  )?.id ?? null
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
    if (chat.activeAgentId === LITERATURE_READER_AGENT_ID && selectedDocumentIds.length === 0) {
      setAttachmentError('请先选择至少一篇已就绪文献。')
      return
    }
    setAttachmentError(null)
    const submittedDraft = draft
    const submittedImages = pendingImages
    setDraft('')
    setPendingImages([])

    const sent = await chat.sendMessage(message, submittedImages, selectedDocumentIds)
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
        agentDirectoryOpen={agentDirectoryOpen}
        onCreate={openAgentSelection}
        onOpenAgentDirectory={openAgentDirectory}
        onSelect={(conversationId) => {
          setPendingImages([])
          setSelectedDocumentIds([])
          setAttachmentError(null)
          setNewConversationReady(false)
          setAgentSelectionOpen(false)
          setMainView('workspace')
          chat.selectConversation(conversationId)
        }}
        onLoadMore={() => { void chat.loadMoreConversations() }}
        onRetry={() => { void chat.refreshConversations() }}
      />

      <section className="chat-main">
        {agentDirectoryOpen && (
          <AgentDirectory
            agents={chat.agents}
            loading={chat.agentsLoading}
            error={chat.agentsError}
            canReturnToConversation={Boolean(chat.activeConversationId) || newConversationReady}
            returnLabel={chat.activeConversationId ? '返回当前对话' : '返回新对话'}
            onSelect={selectAgent}
            onOpenGame={openGame}
            onReturnToConversation={() => setMainView('workspace')}
            onRetry={() => { void chat.loadAgents() }}
          />
        )}
        {mainView === 'game' && (
          <Suspense fallback={<p className="dino-run-loading" role="status">正在加载《徐坤快跑》…</p>}>
            <DinoRunPage onReturnToMarket={openAgentDirectory} />
          </Suspense>
        )}
        <div className={`chat-workspace ${mainView !== 'workspace' ? 'is-hidden' : ''}`} aria-hidden={mainView !== 'workspace'}>
          <header className="chat-topbar">
            <div className="topbar-title">
              <button
                className="mobile-brand-button"
                type="button"
                onClick={openAgentDirectory}
                aria-label="浏览所有智能体"
                title="浏览所有智能体"
              >
                <img className="mobile-brand-mark" src="/brand/nexusai-icon.png" alt="" />
              </button>
              <div>
                <strong>{chat.activeConversation?.title || (chat.activeConversationId ? '会话' : '新对话')}</strong>
                <span><i className="status-dot" /> {activeAgentName} · {chat.status}</span>
              </div>
            </div>
            <button className="mobile-new-conversation" type="button" onClick={openAgentSelection} disabled={chat.sending}>＋ 新对话</button>
          </header>

          <div className="chat-content">
            {chat.activeAgentId === LITERATURE_READER_AGENT_ID && (
              <LiteratureLibraryPanel
                conversationId={chat.activeConversationId}
                assistantResponseId={latestAssistantResponseId}
                sending={chat.sending}
                disabled={chat.sending || Boolean(chat.pendingQuestion)}
                onSelectedDocumentIdsChange={setSelectedDocumentIds}
              />
            )}
            {chat.olderCursor !== null && !chat.historyLoading && (
              <button className="load-older-button" type="button" onClick={() => { void chat.loadOlderMessages() }} disabled={chat.loadingOlder}>
                {chat.loadingOlder ? '正在加载…' : '↑ 查看更早消息'}
              </button>
            )}
            <MessageList
              messages={chat.messages}
              loading={chat.historyLoading}
              conversationId={chat.activeConversationId}
              agentId={chat.activeAgentId || COMMON_AGENT_ID}
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
        </div>
      </section>
      <AgentSelectionDialog
        open={agentSelectionOpen}
        canCancel={Boolean(chat.activeConversationId) || newConversationReady || agentDirectoryOpen}
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
