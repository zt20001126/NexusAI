import type { AgentDefinition } from '../api/agent'
import type { AgentType } from '../constants'
import AgentAvatar from './AgentAvatar'

interface AgentDirectoryProps {
  agents: AgentDefinition[]
  loading: boolean
  error: string | null
  canReturnToConversation: boolean
  returnLabel: string
  onSelect: (agent: AgentType) => void
  onOpenGame: () => void
  onReturnToConversation: () => void
  onRetry: () => void
}

/** 在聊天主区域介绍当前已注册的智能体。 */
function AgentDirectory({
  agents,
  loading,
  error,
  canReturnToConversation,
  returnLabel,
  onSelect,
  onOpenGame,
  onReturnToConversation,
  onRetry,
}: AgentDirectoryProps) {
  return (
    <section className="agent-directory" aria-labelledby="agent-directory-title">
      <div className="agent-directory-heading">
        <div className="agent-directory-heading-top">
          <div className="agent-directory-eyebrow">
            <img src="/brand/nexusai-icon.png" alt="" />
            <span>NEXUSAI 智能体市场</span>
          </div>
          {canReturnToConversation && (
            <button className="agent-directory-return" type="button" onClick={onReturnToConversation}>
              {returnLabel}
            </button>
          )}
        </div>
        <h1 id="agent-directory-title">找到适合你的智能助手</h1>
        <p>选择一个智能体开始新对话，或进入小游戏放松一下。</p>
        {!loading && !error && agents.length > 0 && (
          <span className="agent-directory-count">{agents.length} 个智能体</span>
        )}
      </div>

      <div className="agent-directory-grid">
        <button
          className="agent-directory-card agent-directory-game-card"
          type="button"
          onClick={onOpenGame}
          aria-label="打开徐坤快跑小游戏"
        >
          <span className="agent-directory-card-top">
            <span className="agent-directory-avatar agent-directory-game-avatar" aria-hidden="true" />
            <span className="agent-directory-arrow" aria-hidden="true">↗</span>
          </span>
          <strong className="agent-directory-name">徐坤快跑</strong>
          <span className="agent-directory-description">操控蔡徐坤卡通角色躲避障碍，坚持更久，刷新你的最长记录。</span>
          <span className="agent-directory-capabilities"><span>小游戏</span></span>
          <span className="agent-directory-action">开始游戏 <span aria-hidden="true">→</span></span>
        </button>

        {!loading && !error && agents.map((agent) => (
          <button
            className="agent-directory-card"
            type="button"
            key={agent.agent}
            onClick={() => onSelect(agent.agent)}
            aria-label={`选择${agent.name}：${agent.description}`}
          >
            <span className="agent-directory-card-top">
              <span className="agent-directory-avatar" aria-hidden="true">
                <AgentAvatar agent={agent.agent} />
              </span>
              <span className="agent-directory-arrow" aria-hidden="true">↗</span>
            </span>
            <strong className="agent-directory-name">{agent.name}</strong>
            <span className="agent-directory-description">{agent.description}</span>
            <span className="agent-directory-capabilities">
              {agent.supports_image_upload && <span>支持图片</span>}
              {agent.supports_document_upload && <span>支持文献</span>}
              {!agent.supports_image_upload && !agent.supports_document_upload && <span>智能对话</span>}
            </span>
            <span className="agent-directory-action">开始对话 <span aria-hidden="true">→</span></span>
          </button>
        ))}
      </div>

      {loading && <p className="agent-directory-state" role="status">正在加载智能体…</p>}
      {error && (
        <div className="agent-directory-error" role="alert">
          <p>{error}</p>
          <button type="button" onClick={onRetry}>重新加载</button>
        </div>
      )}
      {!loading && !error && agents.length === 0 && <p className="agent-directory-state" role="status">当前没有可用的智能体。</p>}
    </section>
  )
}

export default AgentDirectory
