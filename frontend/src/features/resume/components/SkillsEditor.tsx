import RichTextEditor from './RichTextEditor'
import type { TiptapDocument } from '../model/types'

interface SkillsEditorProps {
  skills: TiptapDocument
  disabled?: boolean
  onChange: (skills: TiptapDocument) => void
}

function SkillsEditor({ skills, disabled = false, onChange }: SkillsEditorProps) {
  return (
    <div className="resume-editor-section">
      <div className="resume-editor-section-heading">
        <div>
          <p className="resume-editor-eyebrow">SKILLS</p>
          <h2>专业技能</h2>
          <p>在一个编辑框中填写全部技能，支持文字格式和列表。</p>
        </div>
      </div>
      <RichTextEditor
        mode="rich"
        label="专业技能内容"
        value={skills}
        disabled={disabled}
        onChange={onChange}
      />
    </div>
  )
}

export default SkillsEditor
