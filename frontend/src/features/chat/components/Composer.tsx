import { useEffect, useRef, useState } from 'react'
import type { AgentDefinition } from '../api/agent'

interface ComposerProps {
  value: string
  disabled: boolean
  onChange: (value: string) => void
  onSend: () => void
  onCancel: () => void
  canCancel: boolean
  agents: AgentDefinition[]
  activeAgentId: string
  onSelectAgent: (agentId: string) => void
  supportsImageUpload: boolean
  attachments: File[]
  onAddAttachments: (files: File[]) => void
  onRemoveAttachment: (index: number) => void
}

/** 受控消息输入框，支持回车发送、Shift+Enter 换行和停止运行。 */
function Composer({
  value,
  disabled,
  onChange,
  onSend,
  onCancel,
  canCancel,
  agents,
  activeAgentId,
  onSelectAgent,
  supportsImageUpload,
  attachments,
  onAddAttachments,
  onRemoveAttachment,
}: ComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const agentPickerRef = useRef<HTMLDivElement>(null)
  const agentTriggerRef = useRef<HTMLButtonElement>(null)
  const agentOptionRefs = useRef<Array<HTMLButtonElement | null>>([])
  const [previewUrls, setPreviewUrls] = useState<string[]>([])
  const [agentMenuOpen, setAgentMenuOpen] = useState(false)
  const activeAgent = agents.find((agent) => agent.agent_id === activeAgentId)
  const activeAgentIndex = agents.findIndex((agent) => agent.agent_id === activeAgentId)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`
  }, [value])

  useEffect(() => {
    const urls = attachments.map((file) => URL.createObjectURL(file))
    setPreviewUrls(urls)
    return () => urls.forEach((url) => URL.revokeObjectURL(url))
  }, [attachments])

  useEffect(() => {
    if (!agentMenuOpen) return
    function closeWhenOutside(event: PointerEvent) {
      if (event.target instanceof Node && !agentPickerRef.current?.contains(event.target)) {
        setAgentMenuOpen(false)
      }
    }
    document.addEventListener('pointerdown', closeWhenOutside)
    return () => document.removeEventListener('pointerdown', closeWhenOutside)
  }, [agentMenuOpen])

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!disabled && (value.trim() || attachments.length > 0)) onSend()
    }
  }

  function focusAgentOption(index: number) {
    const targetIndex = Math.min(Math.max(index, 0), agents.length - 1)
    if (targetIndex < 0) return
    setAgentMenuOpen(true)
    requestAnimationFrame(() => agentOptionRefs.current[targetIndex]?.focus())
  }

  function handleAgentTriggerKeyDown(event: React.KeyboardEvent<HTMLButtonElement>) {
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault()
      focusAgentOption(activeAgentIndex >= 0 ? activeAgentIndex : 0)
    } else if (event.key === 'Escape' && agentMenuOpen) {
      event.preventDefault()
      setAgentMenuOpen(false)
    }
  }

  function handleAgentOptionKeyDown(
    event: React.KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      focusAgentOption((index + 1) % agents.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      focusAgentOption((index - 1 + agents.length) % agents.length)
    } else if (event.key === 'Home') {
      event.preventDefault()
      focusAgentOption(0)
    } else if (event.key === 'End') {
      event.preventDefault()
      focusAgentOption(agents.length - 1)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setAgentMenuOpen(false)
      agentTriggerRef.current?.focus()
    }
  }

  function selectAgent(agentId: string) {
    if (agentId !== activeAgentId) onSelectAgent(agentId)
    setAgentMenuOpen(false)
    agentTriggerRef.current?.focus()
  }

  return (
    <div className="composer-wrap">
      {attachments.length > 0 && (
        <div className="composer-attachments" aria-label="待发送参考图片">
          {attachments.map((file, index) => (
            <div className="composer-attachment" key={`${file.name}-${file.lastModified}-${index}`}>
              {previewUrls[index] && <img src={previewUrls[index]} alt={file.name} />}
              <span title={file.name}>{file.name}</span>
              <button
                type="button"
                onClick={() => onRemoveAttachment(index)}
                disabled={disabled}
                aria-label={`移除 ${file.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}
      <div className="composer-box">
        <div className="composer-input-row">
          {supportsImageUpload && (
            <>
              <input
                ref={fileInputRef}
                className="composer-file-input"
                type="file"
                accept="image/png,image/jpeg"
                multiple
                onChange={(event) => {
                  onAddAttachments(Array.from(event.currentTarget.files ?? []))
                  event.currentTarget.value = ''
                }}
                disabled={disabled}
                aria-label="选择参考图片"
              />
              <button
                className="attach-button"
                type="button"
                onClick={() => fileInputRef.current?.click()}
                disabled={disabled || attachments.length >= 20}
                aria-label="添加参考图片"
                title="添加参考图片"
              >
                ＋
              </button>
            </>
          )}
          <textarea
            ref={inputRef}
            value={value}
            onChange={(event) => onChange(event.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="给 NexusAI 发消息…"
            rows={1}
            disabled={disabled}
            aria-label="输入消息"
          />
          {canCancel ? (
            <button className="stop-button" type="button" onClick={onCancel} aria-label="停止生成" title="停止生成">■</button>
          ) : (
            <button
              className="send-button"
              type="button"
              onClick={onSend}
              disabled={disabled || (!value.trim() && attachments.length === 0)}
              aria-label="发送消息"
              title="发送消息"
            >
              ↑
            </button>
          )}
        </div>
        <div className="composer-tools-row">
          <div
            className="composer-agent-picker"
            ref={agentPickerRef}
            onBlur={(event) => {
              const nextTarget = event.relatedTarget
              if (!(nextTarget instanceof Node) || !event.currentTarget.contains(nextTarget)) {
                setAgentMenuOpen(false)
              }
            }}
          >
            <button
              ref={agentTriggerRef}
              className="composer-agent-trigger"
              type="button"
              onClick={() => setAgentMenuOpen((open) => !open)}
              onKeyDown={handleAgentTriggerKeyDown}
              disabled={disabled || agents.length === 0}
              aria-label={`当前助手：${activeAgent?.name ?? '未选择'}`}
              aria-haspopup="listbox"
              aria-expanded={agentMenuOpen}
              aria-controls="composer-agent-options"
            >
              <span className="composer-agent-icon" aria-hidden="true">✦</span>
              <span className="composer-agent-name">{activeAgent?.name ?? '选择助手'}</span>
              <span className="composer-agent-chevron" aria-hidden="true" />
            </button>
            {agentMenuOpen && (
              <div
                id="composer-agent-options"
                className="composer-agent-menu"
                role="listbox"
                aria-label="可用助手"
              >
                {agents.map((agent, index) => {
                  const selected = agent.agent_id === activeAgentId
                  return (
                    <button
                      ref={(element) => { agentOptionRefs.current[index] = element }}
                      key={agent.agent_id}
                      className={`composer-agent-option${selected ? ' is-selected' : ''}`}
                      type="button"
                      role="option"
                      aria-selected={selected}
                      onKeyDown={(event) => handleAgentOptionKeyDown(event, index)}
                      onClick={() => selectAgent(agent.agent_id)}
                    >
                      <span className="composer-agent-option-icon" aria-hidden="true">✦</span>
                      <span className="composer-agent-option-copy">
                        <strong>{agent.name}</strong>
                        <small>{agent.description}</small>
                      </span>
                      {selected && <span className="composer-agent-check" aria-hidden="true">✓</span>}
                    </button>
                  )
                })}
              </div>
            )}
          </div>
        </div>
      </div>
      <div className="composer-caption">
        {supportsImageUpload ? '可添加最多 20 张 PNG/JPEG 参考图 · ' : ''}Enter 发送 · Shift + Enter 换行
      </div>
    </div>
  )
}

export default Composer
