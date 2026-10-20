import type { ResumeSection } from '../model/types'
import ResumeSectionIcon from './ResumeSectionIcon'
import type { ResumeSectionIconName } from './ResumeSectionIcon'

const sections: Array<{ id: ResumeSection; label: string; number: string; icon: ResumeSectionIconName }> = [
  { id: 'basic', label: '基本信息', number: '01', icon: 'profile' },
  { id: 'education', label: '教育背景', number: '02', icon: 'education' },
  { id: 'skills', label: '专业技能', number: '03', icon: 'skills' },
  { id: 'work', label: '工作经历', number: '04', icon: 'work' },
  { id: 'projects', label: '项目经历', number: '05', icon: 'projects' },
  { id: 'style', label: '排版设置', number: '06', icon: 'style' },
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
          <span className="resume-navigation-number">{section.number}</span>
          <ResumeSectionIcon name={section.icon} className="resume-navigation-icon" />
          <strong>{section.label}</strong>
          <span className="resume-navigation-arrow" aria-hidden="true">›</span>
        </button>
      ))}
    </nav>
  )
}

export default ResumeSectionNavigation
