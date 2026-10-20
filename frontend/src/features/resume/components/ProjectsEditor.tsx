import RichTextEditor from './RichTextEditor'
import { createEmptyTiptapDocument, type ProjectItem } from '../model/types'

interface ProjectsEditorProps {
  items: ProjectItem[]
  disabled?: boolean
  onChange: (items: ProjectItem[]) => void
}

function ProjectsEditor({ items, disabled = false, onChange }: ProjectsEditorProps) {
  function update(id: string, patch: Partial<ProjectItem>) {
    onChange(items.map((item) => item.id === id ? { ...item, ...patch } : item))
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div><p className="resume-editor-eyebrow">PROJECTS</p><h2>项目经历</h2><p>突出项目目标、个人贡献和使用的技术。</p></div>
        <span className="resume-item-count">{items.length} / 20</span>
      </div>
      <div className="resume-entry-editor-list">
        {items.map((item, index) => (
          <article className="resume-editor-card" key={item.id}>
            <div className="resume-item-card-heading">
              <strong>项目经历 {String(index + 1).padStart(2, '0')}</strong>
              <button className="resume-icon-button is-danger" type="button" disabled={disabled} aria-label={`删除项目经历 ${index + 1}`} onClick={() => onChange(items.filter((entry) => entry.id !== item.id))}>删除</button>
            </div>
            <div className="resume-form-grid">
              <label className="resume-field resume-field-span"><span>项目名称 <em>*</em></span><input maxLength={120} value={item.name} disabled={disabled} onChange={(event) => update(item.id, { name: event.target.value })} placeholder="项目名称" /></label>
              <label className="resume-field"><span>担任角色</span><input maxLength={80} value={item.role} disabled={disabled} onChange={(event) => update(item.id, { role: event.target.value })} placeholder="例如：主要开发" /></label>
              <label className="resume-field"><span>技术栈</span><input maxLength={240} value={item.technology_stack} disabled={disabled} onChange={(event) => update(item.id, { technology_stack: event.target.value })} placeholder="Python、FastAPI" /></label>
              <label className="resume-field"><span>开始时间 <em>*</em></span><input type="month" value={item.start_month} disabled={disabled} onChange={(event) => update(item.id, { start_month: event.target.value })} /></label>
              <label className="resume-field"><span>结束时间 <em>*</em></span><input type="month" value={item.end_month} disabled={disabled} onChange={(event) => update(item.id, { end_month: event.target.value })} /></label>
              <div className="resume-field resume-field-span"><span>项目描述</span><RichTextEditor mode="rich" value={item.content} disabled={disabled} onChange={(content) => update(item.id, { content })} /></div>
            </div>
          </article>
        ))}
        {items.length === 0 && <p className="resume-empty-inline">还没有添加项目经历。</p>}
      </div>
      <button className="resume-add-button" type="button" disabled={disabled || items.length >= 20} onClick={() => onChange([...items, { id: crypto.randomUUID(), name: '', role: '', technology_stack: '', start_month: '', end_month: '', content: createEmptyTiptapDocument() }])}>
        <span aria-hidden="true">＋</span> 添加项目经历
      </button>
    </div>
  )
}

export default ProjectsEditor
