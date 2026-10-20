import type { ResumeSection } from '../model/types'

const sections: Array<{ id: ResumeSection; label: string; number: string }> = [
  { id: 'basic', label: '基本信息', number: '01' },
  { id: 'education', label: '教育背景', number: '02' },
  { id: 'skills', label: '专业技能', number: '03' },
  { id: 'work', label: '工作经历', number: '04' },
  { id: 'projects', label: '项目经历', number: '05' },
  { id: 'style', label: '排版设置', number: '06' },
]

interface ResumeSectionNavigationProps {
  activeSection: ResumeSection
  disabled?: boolean
  onChange: (section: ResumeSection) => void
}

function ResumeSectionNavigation({ activeSection, disabled = false, onChange }: ResumeSectionNavigationProps) {
  return (
    <nav className="resume-section-navigation" aria-label="简历编辑模块">
      <p className="resume-navigation-eyebrow">内容模块</p>
      {sections.map((section) => (
        <button
          className={`resume-navigation-item ${activeSection === section.id ? 'is-active' : ''}`}
          type="button"
          key={section.id}
          aria-current={activeSection === section.id ? 'step' : undefined}
          disabled={disabled}
          onClick={() => onChange(section.id)}
        >
          <span>{section.number}</span>
          <strong>{section.label}</strong>
          <span className="resume-navigation-arrow" aria-hidden="true">›</span>
        </button>
      ))}
      <div className="resume-navigation-help">
        <span aria-hidden="true">✦</span>
        <p>边编辑边预览，保存后即可导出单页 PDF。</p>
      </div>
    </nav>
  )
}

export default ResumeSectionNavigation
