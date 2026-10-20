import type { ResumeDraft, ResumeSection, ResumeStyleConfig } from '../model/types'
import BasicInfoEditor from './BasicInfoEditor'
import EducationEditor from './EducationEditor'
import ProjectsEditor from './ProjectsEditor'
import SkillsEditor from './SkillsEditor'
import StyleSettingsEditor from './StyleSettingsEditor'
import WorkExperienceEditor from './WorkExperienceEditor'

interface ResumeEditorPanelProps {
  section: ResumeSection
  draft: ResumeDraft
  photoPreviewUrl: string | null
  photoError: string | null
  disabled?: boolean
  onUpdateContent: ResumePageContentUpdater
  onUpdateStyle: (value: ResumeStyleConfig) => void
  onUploadPhoto: (file: File) => Promise<void>
  onRemovePhoto: () => void
}

type ResumePageContentUpdater = <K extends keyof ResumeDraft['content']>(field: K, value: ResumeDraft['content'][K]) => void

function ResumeEditorPanel({
  section,
  draft,
  photoPreviewUrl,
  photoError,
  disabled = false,
  onUpdateContent,
  onUpdateStyle,
  onUploadPhoto,
  onRemovePhoto,
}: ResumeEditorPanelProps) {
  return (
    <section className="resume-editor-panel" aria-label="简历内容编辑">
      {section === 'basic' && <BasicInfoEditor value={draft.content.basic_info} photoPreviewUrl={photoPreviewUrl} disabled={disabled} onChange={(value) => onUpdateContent('basic_info', value)} onUploadPhoto={onUploadPhoto} onRemovePhoto={onRemovePhoto} />}
      {section === 'education' && <EducationEditor items={draft.content.educations} disabled={disabled} onChange={(items) => onUpdateContent('educations', items)} />}
      {section === 'skills' && <SkillsEditor skills={draft.content.skills} disabled={disabled} onChange={(items) => onUpdateContent('skills', items)} />}
      {section === 'work' && <WorkExperienceEditor items={draft.content.works} disabled={disabled} onChange={(items) => onUpdateContent('works', items)} />}
      {section === 'projects' && <ProjectsEditor items={draft.content.projects} disabled={disabled} onChange={(items) => onUpdateContent('projects', items)} />}
      {section === 'style' && <StyleSettingsEditor value={draft.style_config} disabled={disabled} onChange={onUpdateStyle} />}
      {photoError && section === 'basic' && <p className="resume-form-error" role="alert">{photoError}</p>}
    </section>
  )
}

export default ResumeEditorPanel
