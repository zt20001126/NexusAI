import type { EducationItem } from '../model/types'

interface EducationEditorProps {
  items: EducationItem[]
  disabled?: boolean
  onChange: (items: EducationItem[]) => void
}

function EducationEditor({ items, disabled = false, onChange }: EducationEditorProps) {
  function update(id: string, patch: Partial<EducationItem>) {
    onChange(items.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div>
          <p className="resume-editor-eyebrow">EDUCATION</p>
          <h2>教育背景</h2>
          <p>按时间顺序添加学校、专业和就读时间。</p>
        </div>
        <span className="resume-item-count">{items.length} / 10</span>
      </div>
      <div className="resume-entry-editor-list">
        {items.map((item, index) => (
          <article className="resume-editor-card" key={item.id}>
            <div className="resume-item-card-heading">
              <strong>教育经历 {String(index + 1).padStart(2, '0')}</strong>
              <button className="resume-icon-button is-danger" type="button" disabled={disabled} aria-label={`删除教育经历 ${index + 1}`} onClick={() => onChange(items.filter((entry) => entry.id !== item.id))}>删除</button>
            </div>
            <div className="resume-form-grid">
              <label className="resume-field resume-field-span"><span>学校 <em>*</em></span><input maxLength={120} value={item.school} disabled={disabled} onChange={(event) => update(item.id, { school: event.target.value })} placeholder="学校名称" /></label>
              <label className="resume-field"><span>专业</span><input maxLength={120} value={item.major} disabled={disabled} onChange={(event) => update(item.id, { major: event.target.value })} placeholder="专业名称" /></label>
              <label className="resume-field"><span>学历</span><input maxLength={120} value={item.degree} disabled={disabled} onChange={(event) => update(item.id, { degree: event.target.value })} placeholder="本科 / 硕士" /></label>
              <label className="resume-field"><span>开始时间 <em>*</em></span><input type="month" value={item.start_month} disabled={disabled} onChange={(event) => update(item.id, { start_month: event.target.value })} /></label>
              <label className="resume-field"><span>结束时间 <em>*</em></span><input type="month" value={item.end_month} disabled={disabled} onChange={(event) => update(item.id, { end_month: event.target.value })} /></label>
            </div>
          </article>
        ))}
        {items.length === 0 && <p className="resume-empty-inline">还没有添加教育经历。</p>}
      </div>
      <button className="resume-add-button" type="button" disabled={disabled || items.length >= 10} onClick={() => onChange([...items, { id: crypto.randomUUID(), school: '', major: '', degree: '', start_month: '', end_month: '' }])}>
        <span aria-hidden="true">＋</span> 添加教育经历
      </button>
    </div>
  )
}

export default EducationEditor
