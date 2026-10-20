import { useState } from 'react'
import RichTextEditor from './RichTextEditor'

interface SkillRow {
  key: string
  value: string
}

interface SkillsEditorProps {
  skills: string[]
  disabled?: boolean
  onChange: (skills: string[]) => void
}

function SkillsEditor({ skills, disabled = false, onChange }: SkillsEditorProps) {
  const [rows, setRows] = useState<SkillRow[]>(() =>
    skills.map((value) => ({ key: crypto.randomUUID(), value })),
  )

  function updateRows(next: SkillRow[]) {
    setRows(next)
    onChange(next.map((row) => row.value))
  }

  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div>
          <p className="resume-editor-eyebrow">SKILLS</p>
          <h2>专业技能</h2>
          <p>每项技能单独编辑为一段纯文本，最多 20 项。</p>
        </div>
        <span className="resume-item-count">{rows.length} / 20</span>
      </div>
      <div className="resume-skill-list">
        {rows.map((row, index) => (
          <article className="resume-skill-card" key={row.key}>
            <div className="resume-item-card-heading">
              <strong>技能 {String(index + 1).padStart(2, '0')}</strong>
              <button
                className="resume-icon-button is-danger"
                type="button"
                aria-label={`删除技能 ${index + 1}`}
                disabled={disabled}
                onClick={() => updateRows(rows.filter((item) => item.key !== row.key))}
              >
                删除
              </button>
            </div>
            <RichTextEditor
              mode="plain"
              value={row.value}
              disabled={disabled}
              onChange={(value) => updateRows(rows.map((item) => item.key === row.key ? { ...item, value } : item))}
            />
          </article>
        ))}
        {rows.length === 0 && <p className="resume-empty-inline">还没有添加技能，点击下方按钮开始。</p>}
      </div>
      <button
        className="resume-add-button"
        type="button"
        disabled={disabled || rows.length >= 20}
        onClick={() => updateRows([...rows, { key: crypto.randomUUID(), value: '' }])}
      >
        <span aria-hidden="true">＋</span> 添加一项技能
      </button>
    </div>
  )
}

export default SkillsEditor
