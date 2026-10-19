import { useEffect, useRef, useState } from 'react'
import { MAX_REFERENCE_IMAGES } from '../constants'

interface ComposerProps {
  value: string
  disabled: boolean
  sending: boolean
  onChange: (value: string) => void
  onSend: () => void
  onCancel: () => void
  canCancel: boolean
  supportsImageUpload: boolean
  attachments: File[]
  onAddAttachments: (files: File[]) => void
  onRemoveAttachment: (index: number) => void
}

/** 受控消息输入框，支持回车发送、Shift+Enter 换行和停止运行。 */
function Composer({
  value,
  disabled,
  sending,
  onChange,
  onSend,
  onCancel,
  canCancel,
  supportsImageUpload,
  attachments,
  onAddAttachments,
  onRemoveAttachment,
}: ComposerProps) {
  const inputRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [previewUrls, setPreviewUrls] = useState<string[]>([])
  const interactionDisabled = disabled || sending

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

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault()
      if (!interactionDisabled && (value.trim() || attachments.length > 0)) onSend()
    }
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
                disabled={interactionDisabled}
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
                disabled={interactionDisabled || attachments.length >= MAX_REFERENCE_IMAGES}
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
            readOnly={sending}
            aria-disabled={interactionDisabled}
            placeholder="给 NexusAI 发消息…"
            rows={1}
            disabled={disabled}
            aria-label="输入消息"
          />
          {canCancel ? (
            <button className="stop-button" type="button" onMouseDown={(event) => event.preventDefault()} onClick={onCancel} aria-label="停止生成" title="停止生成">■</button>
          ) : (
            <button
              className="send-button"
              type="button"
              onMouseDown={(event) => event.preventDefault()}
              onClick={onSend}
              disabled={interactionDisabled || (!value.trim() && attachments.length === 0)}
              aria-label="发送消息"
              title="发送消息"
            >
              ↑
            </button>
          )}
        </div>
      </div>
      <div className="composer-caption">
        {supportsImageUpload ? '最多添加 3 张 PNG/JPEG 参考图，每张不超过 5 MiB · ' : ''}Enter 发送 · Shift + Enter 换行
      </div>
    </div>
  )
}

export default Composer
