import { useState } from 'react'
import { getApiDocsUrl } from '../../shared/api/http'
import AgentInteractionCard from './components/AgentInteractionCard'
import Composer from './components/Composer'
import ConversationSidebar from './components/ConversationSidebar'
import MessageList from './components/MessageList'
import { useChatSession } from './hooks/useChatSession'

/** 组合聊天页面的导航、消息流、追问卡片和输入框。 */
function ChatPage() {
  const [draft, setDraft] = useState('')
  const chat = useChatSession()

  async function handleSend() {
    const message = draft.trim()
    if (!message || chat.sending) return
    setDraft('')
    await chat.sendMessage(message)
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
        onCreate={chat.createConversation}
        onSelect={chat.selectConversation}
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
          {chat.error && <div className="error-banner" role="alert">{chat.error}</div>}
        </div>

        <Composer
          value={draft}
          disabled={chat.sending || Boolean(chat.pendingQuestion)}
          onChange={setDraft}
          onSend={() => { void handleSend() }}
          onCancel={() => { void chat.cancelRun() }}
          canCancel={chat.canCancel}
        />
      </section>
    </main>
  )
}

export default ChatPage
