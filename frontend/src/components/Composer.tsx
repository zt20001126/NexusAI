import { useEffect, useRef } from 'react'

interface ComposerProps {
  value: string
  disabled: boolean
  onChange: (value: string) => void
  onSend: () => void
  onCancel: () => void
  canCancel: boolean
}

/** 受控消息输入框，支持回车发送、Shift+Enter 换行和停止运行。 */
function Composer({ value, disabled, onChange, onSend, onCancel, canCancel }: ComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    const input = inputRef.current
    if (!input) return
    input.style.height = 'auto'
    input.style.height = `${Math.min(input.scrollHeight, 180)}px`
  }, [value])

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!disabled && value.trim()) onSend()
    }
  }

  return (
    <div className="composer-wrap">
      <div className="composer-box">
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
            disabled={disabled || !value.trim()}
            aria-label="发送消息"
            title="发送消息"
          >
            ↑
          </button>
        )}
      </div>
      <div className="composer-caption">Enter 发送 · Shift + Enter 换行</div>
    </div>
  )
}

export default Composer
