import { useLayoutEffect, useRef } from 'react'
import type { AgentDefinition } from '../api/agent'
import type { AgentType } from '../constants'
import AgentAvatar from '../../../shared/components/AgentAvatar'

interface AgentSelectionDialogProps {
  open: boolean
  canCancel: boolean
  agents: AgentDefinition[]
  agentsLoading: boolean
  agentsError: string | null
  onSelect: (agent: AgentType) => void
  onCancel: () => void
  onRetry: () => void
}

/** 新建会话前选择智能体；有当前会话时允许取消并返回。 */
function AgentSelectionDialog({
  open,
  canCancel,
  agents,
  agentsLoading,
  agentsError,
  onSelect,
  onCancel,
  onRetry,
}: AgentSelectionDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null)

  useLayoutEffect(() => {
    const dialog = dialogRef.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    else if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={dialogRef}
      className="agent-selection-dialog"
      aria-labelledby="agent-selection-title"
      onCancel={(event) => {
        event.preventDefault()
        if (canCancel) onCancel()
      }}
      onClick={(event) => {
        if (event.target === event.currentTarget && canCancel) onCancel()
      }}
    >
      <div className="agent-selection-heading">
        <div>
          <h2 id="agent-selection-title">选择智能体</h2>
          <p>选择一个智能体，开始新对话</p>
        </div>
        {canCancel && (
          <button
            className="agent-selection-close"
            type="button"
            onClick={onCancel}
            aria-label="返回当前对话"
          >
            ×
          </button>
        )}
      </div>

      {agentsLoading ? (
        <p className="agent-selection-state" role="status">正在读取可用智能体…</p>
      ) : agentsError ? (
        <div className="agent-selection-error" role="alert">
          <p>{agentsError}</p>
          <button type="button" onClick={onRetry}>重新加载</button>
        </div>
      ) : agents.length > 0 ? (
        <div className="agent-selection-options">
          {agents.map((agent) => (
            <button
              className="agent-selection-option"
              type="button"
              key={agent.agent}
              onClick={() => onSelect(agent.agent)}
            >
              <span className="agent-selection-option-icon" aria-hidden="true">
                <AgentAvatar agent={agent.agent} />
              </span>
              <span className="agent-selection-option-copy">
                <strong>{agent.name}</strong>
                <small>{agent.description}</small>
              </span>
            </button>
          ))}
        </div>
      ) : (
        <p className="agent-selection-state" role="status">当前没有可用的智能体。</p>
      )}

      {canCancel && (
        <div className="agent-selection-footer">
          <button className="agent-selection-cancel" type="button" onClick={onCancel}>
            返回当前对话
          </button>
        </div>
      )}
    </dialog>
  )
}

export default AgentSelectionDialog
