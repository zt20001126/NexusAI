import { useState } from 'react'
import './styles/resume.css'
import { downloadResumePdf } from './api/resume'
import RobotAvatar, { RESUME_ASSISTANT_AVATAR_SEED } from '../../shared/components/RobotAvatar'
import ResumeEditorPanel from './components/ResumeEditorPanel'
import ResumePreview from './components/ResumePreview'
import ResumeSectionNavigation from './components/ResumeSectionNavigation'
import JobChatPanel from '../chat/components/JobChatPanel'
import { useResumeEditor } from './hooks/useResumeEditor'
import type { ResumeSection } from './model/types'

interface ResumePageProps {
  onBack: () => void
}

function ResumePage({ onBack }: ResumePageProps) {
  const [activeSection, setActiveSection] = useState<ResumeSection>('basic')
  const [exporting, setExporting] = useState(false)
  const [exportError, setExportError] = useState<string | null>(null)
  const editor = useResumeEditor()

  function handleBack() {
    if (editor.confirmLeave()) onBack()
  }

  async function handleSave() {
    setExportError(null)
    await editor.save()
  }

  async function handleExport() {
    setExportError(null)
    if (editor.dirty) {
      const shouldSave = window.confirm('简历有未保存的修改。保存成功后继续导出 PDF？')
      if (!shouldSave) return
      const saved = await editor.save()
      if (!saved) return
    }
    setExporting(true)
    try {
      await downloadResumePdf()
    } catch (error) {
      setExportError(error instanceof Error ? error.message : 'PDF 导出失败，请重试。')
    } finally {
      setExporting(false)
    }
  }

  if (editor.loadError) {
    return (
      <main className="resume-app-shell">
        <div className="resume-load-error">
          <span className="resume-load-error-icon" aria-hidden="true">!</span>
          <h1>简历暂时无法加载</h1>
          <p>{editor.loadError}</p>
          <button className="resume-primary-button" type="button" onClick={() => { void editor.load() }}>重新加载</button>
          <button className="resume-link-button" type="button" onClick={handleBack}>返回智能体市场</button>
        </div>
      </main>
    )
  }

  return (
    <main className="resume-app-shell">
      <header className="resume-app-header">
        <div className="resume-app-brand">
          <button className="resume-back-button" type="button" onClick={handleBack} aria-label="返回智能体市场">
            <span aria-hidden="true">←</span>
          </button>
          <span className="resume-brand-avatar" aria-hidden="true"><RobotAvatar seed={RESUME_ASSISTANT_AVATAR_SEED} /></span>
          <div><strong>简历助手</strong><span>RESUME ASSISTANT</span></div>
        </div>
        <div className="resume-header-actions">
          <span className={`resume-save-indicator ${editor.dirty ? 'is-dirty' : editor.savedResume?.exists ? 'is-saved' : 'is-empty'}`} role="status">
            <i aria-hidden="true" />{editor.dirty ? '有未保存修改' : editor.savedResume?.exists ? '内容已保存' : '尚未保存'}
          </span>
          <button className="resume-secondary-button" type="button" disabled={editor.loading || editor.saving || editor.uploadingPhoto || exporting || (!editor.dirty && !editor.savedResume?.exists)} onClick={() => { void handleExport() }}>
            {exporting ? '正在导出…' : '导出 PDF'}
          </button>
          <button className="resume-primary-button" type="button" disabled={editor.loading || editor.saving || editor.uploadingPhoto || exporting || !editor.dirty} onClick={() => { void handleSave() }}>
            {editor.saving ? '正在保存…' : '保存简历'}
          </button>
        </div>
      </header>

      {(editor.saveError || exportError) && (
        <div className="resume-global-error" role="alert">
          <span>{editor.saveError || exportError}</span>
          <button type="button" aria-label="关闭错误提示" onClick={() => { editor.clearSaveError(); setExportError(null) }}>×</button>
        </div>
      )}

      <div className="resume-workspace">
        <ResumeSectionNavigation activeSection={activeSection} disabled={editor.loading || editor.saving} onChange={setActiveSection} />
        <ResumePreview
          content={editor.draft.content}
          style={editor.draft.style_config}
          photoPreviewUrl={editor.photoPreviewUrl}
          exists={Boolean(editor.savedResume?.exists)}
          dirty={editor.dirty}
          loading={editor.loading}
        />
        {activeSection === 'job' ? (
          <JobChatPanel />
        ) : (
          <ResumeEditorPanel
            section={activeSection}
            draft={editor.draft}
            photoPreviewUrl={editor.photoPreviewUrl}
            photoError={editor.photoError}
            disabled={editor.loading || editor.saving || editor.uploadingPhoto}
            onUpdateContent={editor.updateContent}
            onUpdateStyle={editor.updateStyleConfig}
            onUploadPhoto={editor.uploadPhoto}
            onRemovePhoto={editor.removePhoto}
          />
        )}
      </div>
    </main>
  )
}

export default ResumePage
