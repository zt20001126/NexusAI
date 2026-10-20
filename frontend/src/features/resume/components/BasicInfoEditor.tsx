import type { ChangeEvent } from 'react'
import type { BasicInfo } from '../model/types'

interface BasicInfoEditorProps {
  value: BasicInfo
  photoPreviewUrl: string | null
  disabled?: boolean
  onChange: (value: BasicInfo) => void
  onUploadPhoto: (file: File) => Promise<void>
  onRemovePhoto: () => void
}

function BasicInfoEditor({
  value,
  photoPreviewUrl,
  disabled = false,
  onChange,
  onUploadPhoto,
  onRemovePhoto,
}: BasicInfoEditorProps) {
  function change(field: keyof BasicInfo, nextValue: string | null) {
    onChange({ ...value, [field]: nextValue })
  }

  async function handlePhotoChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0]
    event.currentTarget.value = ''
    if (file) await onUploadPhoto(file)
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div>
          <p className="resume-editor-eyebrow">PERSONAL PROFILE</p>
          <h2>基本信息</h2>
          <p>补充联系方式和求职意向，姓名、电话和邮箱为必填项。</p>
        </div>
      </div>

      <div className="resume-photo-editor">
        <div className="resume-photo-preview">
          {photoPreviewUrl ? <img src={photoPreviewUrl} alt="证件照预览" /> : <span aria-hidden="true">照片</span>}
        </div>
        <div>
          <strong>证件照</strong>
          <p>PNG 或 JPEG，最大 5 MiB。照片私有保存。</p>
          <div className="resume-photo-actions">
            <label className={`resume-secondary-button ${disabled ? 'is-disabled' : ''}`}>
              上传照片
              <input
                type="file"
                accept="image/png,image/jpeg"
                disabled={disabled}
                onChange={(event) => { void handlePhotoChange(event) }}
              />
            </label>
            {photoPreviewUrl && (
              <button className="resume-link-button" type="button" disabled={disabled} onClick={onRemovePhoto}>
                移除
              </button>
            )}
          </div>
        </div>
      </div>

      <div className="resume-form-grid">
        <label className="resume-field">
          <span>姓名 <em>*</em></span>
          <input value={value.name} maxLength={80} disabled={disabled} autoComplete="name" onChange={(event) => change('name', event.target.value)} placeholder="例如：张三" />
        </label>
        <label className="resume-field">
          <span>联系电话 <em>*</em></span>
          <input value={value.phone} maxLength={32} disabled={disabled} autoComplete="tel" onChange={(event) => change('phone', event.target.value)} placeholder="例如：138 0000 0000" />
        </label>
        <label className="resume-field resume-field-span">
          <span>邮箱 <em>*</em></span>
          <input type="email" value={value.email} maxLength={254} disabled={disabled} autoComplete="email" onChange={(event) => change('email', event.target.value)} placeholder="name@example.com" />
        </label>
        <label className="resume-field resume-field-span">
          <span>求职意向</span>
          <input value={value.intended_position} maxLength={120} disabled={disabled} onChange={(event) => change('intended_position', event.target.value)} placeholder="例如：后端开发工程师" />
        </label>
        <label className="resume-field">
          <span>出生年月</span>
          <input type="month" value={value.birth_month ?? ''} disabled={disabled} onChange={(event) => change('birth_month', event.target.value || null)} />
        </label>
      </div>
    </div>
  )
}

export default BasicInfoEditor
