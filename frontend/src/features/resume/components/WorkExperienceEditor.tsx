import RichTextEditor from './RichTextEditor'
import { createEmptyTiptapDocument, type WorkItem } from '../model/types'

interface WorkExperienceEditorProps {
  items: WorkItem[]
  disabled?: boolean
  onChange: (items: WorkItem[]) => void
}

function WorkExperienceEditor({ items, disabled = false, onChange }: WorkExperienceEditorProps) {
  function update(id: string, patch: Partial<WorkItem>) {
    onChange(items.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div><p className="resume-editor-eyebrow">EXPERIENCE</p><h2>工作经历</h2><p>描述职责、成果和影响，支持基础富文本格式。</p></div>
        <span className="resume-item-count">{items.length} / 20</span>
      </div>
      <div className="resume-entry-editor-list">
        {items.map((item, index) => (
          <article className="resume-editor-card" key={item.id}>
            <div className="resume-item-card-heading">
              <strong>工作经历 {String(index + 1).padStart(2, '0')}</strong>
              <button className="resume-icon-button is-danger" type="button" disabled={disabled} aria-label={`删除工作经历 ${index + 1}`} onClick={() => onChange(items.filter((entry) => entry.id !== item.id))}>删除</button>
            </div>
            <div className="resume-form-grid">
              <label className="resume-field"><span>公司 <em>*</em></span><input maxLength={120} value={item.company} disabled={disabled} onChange={(event) => update(item.id, { company: event.target.value })} placeholder="公司名称" /></label>
              <label className="resume-field"><span>职位 <em>*</em></span><input maxLength={120} value={item.position} disabled={disabled} onChange={(event) => update(item.id, { position: event.target.value })} placeholder="担任职位" /></label>
              <label className="resume-field"><span>开始时间 <em>*</em></span><input type="month" value={item.start_month} disabled={disabled} onChange={(event) => update(item.id, { start_month: event.target.value })} /></label>
              <label className="resume-field"><span>结束时间 <em>*</em></span><input type="month" value={item.end_month} disabled={disabled} onChange={(event) => update(item.id, { end_month: event.target.value })} /></label>
              <div className="resume-field resume-field-span"><span>工作内容</span><RichTextEditor mode="rich" value={item.content} disabled={disabled} onChange={(content) => update(item.id, { content })} /></div>
            </div>
          </article>
        ))}
        {items.length === 0 && <p className="resume-empty-inline">还没有添加工作经历。</p>}
      </div>
      <button className="resume-add-button" type="button" disabled={disabled || items.length >= 20} onClick={() => onChange([...items, { id: crypto.randomUUID(), company: '', position: '', start_month: '', end_month: '', content: createEmptyTiptapDocument() }])}>
        <span aria-hidden="true">＋</span> 添加工作经历
      </button>
    </div>
  )
}

export default WorkExperienceEditor
