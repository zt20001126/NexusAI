import type { Conversation } from '../api/conversations'

interface ConversationSidebarProps {
  conversations: Conversation[]
  activeConversationId: string | null
  loading: boolean
  hasMore: boolean
  loadingMore: boolean
  disabled: boolean
  error: string | null
  onCreate: () => void
  onSelect: (conversationId: string) => void
  onLoadMore: () => void
  onRetry: () => void
}

/** 左侧会话导航，负责新建、切换以及空态和加载错误展示。 */
function ConversationSidebar({
  conversations,
  activeConversationId,
  loading,
  hasMore,
  loadingMore,
  disabled,
  error,
  onCreate,
  onSelect,
  onLoadMore,
  onRetry,
}: ConversationSidebarProps) {
  return (
    <aside className="sidebar">
      <div className="brand-lockup">
        <img className="brand-mark" src="/brand/nexusai-icon.png" alt="" />
        <div>
          <strong>NexusAI</strong>
        </div>
      </div>

      <button className="new-chat-button" type="button" onClick={onCreate} disabled={disabled}>
        <span aria-hidden="true">＋</span> 开启新对话
      </button>

      <div className="sidebar-section-title">最近会话</div>
      <div className="conversation-list" aria-live="polite">
        {loading && <p className="sidebar-hint">正在加载会话…</p>}
        {!loading && error && (
          <div className="sidebar-error">
            <p>{error}</p>
            <button type="button" onClick={onRetry}>重试</button>
          </div>
        )}
        {!loading && !error && conversations.length === 0 && (
          <p className="sidebar-hint">还没有会话，开始一次新对话吧。</p>
        )}
        {!loading && !error && conversations.map((conversation) => (
          <button
            className={`conversation-item ${activeConversationId === conversation.conversation_id ? 'is-active' : ''}`}
            type="button"
            key={conversation.conversation_id}
            disabled={disabled}
            onClick={() => onSelect(conversation.conversation_id)}
            title={conversation.title ?? '新会话'}
          >
            <span className="conversation-icon" aria-hidden="true">◌</span>
            <span className="conversation-title">{conversation.title || '新会话'}</span>
          </button>
        ))}
        {!loading && !error && hasMore && (
          <button className="load-more-conversations" type="button" onClick={onLoadMore} disabled={disabled || loadingMore}>
            {loadingMore ? '正在加载…' : '加载更多会话'}
          </button>
        )}
      </div>
    </aside>
  )
}

export default ConversationSidebar
