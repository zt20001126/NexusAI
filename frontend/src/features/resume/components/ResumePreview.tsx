import { useEffect, useRef, useState } from 'react'
import type { CSSProperties, ReactNode } from 'react'
import type {
  ResumeContent,
  ResumeStyleConfig,
  TiptapDocument,
  TiptapNode,
} from '../model/types'
import { createResumeProfileSummary } from '../model/profileSummary'
import ResumeSectionIcon from './ResumeSectionIcon'
import type { ResumeSectionIconName } from './ResumeSectionIcon'

interface ResumePreviewProps {
  content: ResumeContent
  style: ResumeStyleConfig
  photoPreviewUrl: string | null
  exists: boolean
  dirty: boolean
  loading: boolean
}

function ResumePreview({ content, style, photoPreviewUrl, exists, dirty, loading }: ResumePreviewProps) {
  const pageRef = useRef<HTMLElement>(null)
  const [overflow, setOverflow] = useState(false)
  const profileSummary = createResumeProfileSummary(content.basic_info, content.educations)

  useEffect(() => {
    const page = pageRef.current
    if (!page) return
    const measure = () => setOverflow(page.scrollHeight > page.clientHeight + 2)
    const observer = new ResizeObserver(measure)
    observer.observe(page)
    window.addEventListener('resize', measure)
    measure()
    return () => {
      observer.disconnect()
      window.removeEventListener('resize', measure)
    }
  }, [content, style, photoPreviewUrl])

  const fontFamily = style.font_family === 'arphic_ukai'
    ? '"AR PL UKai CN", "AR PL UKai HK", "SimSun", serif'
    : '"WenQuanYi Zen Hei", "Microsoft YaHei", sans-serif'

  return (
    <section className="resume-preview-panel" aria-label="A4 简历预览">
      <div className="resume-preview-heading">
        <div><span className="resume-preview-eyebrow">LIVE PREVIEW</span><h2>页面预览</h2></div>
        <span className={`resume-preview-state ${dirty ? 'is-dirty' : exists ? 'is-saved' : 'is-empty'}`}>
          <i aria-hidden="true" />{dirty ? '未保存' : exists ? '已保存' : '尚未保存'}
        </span>
      </div>
      {overflow && <p className="resume-overflow-warning" role="status">内容可能超出单页 A4，导出前请调整内容或排版。</p>}
      <div className="resume-paper-stage">
        <article
          className={`resume-preview-paper ${loading ? 'is-loading' : ''}`}
          ref={pageRef}
          style={{
            fontFamily,
            color: '#202b3c',
            padding: `${style.page_margin_mm.top / 210 * 100}% ${style.page_margin_mm.right / 210 * 100}% ${style.page_margin_mm.bottom / 210 * 100}% ${style.page_margin_mm.left / 210 * 100}%`,
            '--resume-heading-color': style.heading_color,
            '--resume-divider-color': style.divider_color,
            '--resume-divider-width': `${style.divider_width_pt * 0.168}cqw`,
            '--resume-body-font': `${style.font_size_pt * 0.168}cqw`,
            '--resume-line-height': style.line_height,
            '--resume-section-space': `${style.section_spacing_pt * 0.168}cqw`,
            '--resume-paragraph-space': `${style.paragraph_spacing_pt * 0.168}cqw`,
          } as CSSProperties}
        >
          {loading ? (
            <div className="resume-preview-skeleton" aria-label="正在加载简历" />
          ) : (
            <>
              <header className="resume-preview-personal">
                <div>
                  <h1>{content.basic_info.name || '你的姓名'}</h1>
                  {profileSummary.positionItems.length > 0 && <p className="resume-preview-position">{profileSummary.positionItems.join('　|　')}</p>}
                  {profileSummary.contactItems.length > 0 && <p className="resume-preview-contact">{profileSummary.contactItems.join('　|　')}</p>}
                </div>
                {photoPreviewUrl && <img className="resume-preview-photo" src={photoPreviewUrl} alt="证件照" />}
              </header>
              {content.educations.length > 0 && <PreviewSection title="教育背景" icon="education">{content.educations.map((item) => (
                <div className="resume-preview-entry" key={item.id}>
                  <div className="resume-preview-entry-heading"><strong>{item.school}</strong><span>{item.start_month} — {item.end_month}</span></div>
                  <p>{[item.major, item.degree].filter(Boolean).join(' · ')}</p>
                </div>
              ))}</PreviewSection>}
              {hasTiptapText(content.skills) && <PreviewSection title="专业技能" icon="skills"><div className="resume-preview-rich">{renderTiptap(content.skills)}</div></PreviewSection>}
              {content.works.length > 0 && <PreviewSection title="工作经历" icon="work">{content.works.map((item) => (
                <div className="resume-preview-entry" key={item.id}>
                  <div className="resume-preview-entry-heading"><strong>{[item.company, item.position].filter(Boolean).join(' · ')}</strong><span>{item.start_month} — {item.end_month}</span></div>
                  <div className="resume-preview-rich">{renderTiptap(item.content)}</div>
                </div>
              ))}</PreviewSection>}
              {content.projects.length > 0 && <PreviewSection title="项目经历" icon="projects">{content.projects.map((item) => (
                <div className="resume-preview-entry" key={item.id}>
                  <div className="resume-preview-entry-heading"><strong>{item.name}</strong><span>{item.start_month} — {item.end_month}</span></div>
                  {(item.role || item.technology_stack) && <p>{[item.role, item.technology_stack].filter(Boolean).join(' · ')}</p>}
                  <div className="resume-preview-rich">{renderTiptap(item.content)}</div>
                </div>
              ))}</PreviewSection>}
            </>
          )}
        </article>
      </div>
      <p className="resume-preview-footnote">A4 · 单页排版</p>
    </section>
  )
}

function PreviewSection({ title, icon, children }: { title: string; icon: ResumeSectionIconName; children: ReactNode }) {
  return <section className="resume-preview-section"><h2><ResumeSectionIcon name={icon} className="resume-preview-section-icon" />{title}</h2>{children}</section>
}

function renderTiptap(document: TiptapDocument): ReactNode {
  return document.content.map((node, index) => renderNode(node, `${node.type}-${index}`))
}

function hasTiptapText(document: TiptapDocument): boolean {
  return document.content.some(hasNodeText)
}

function hasNodeText(node: TiptapNode): boolean {
  if (node.type === 'text') return node.text.trim().length > 0
  if (node.type === 'hardBreak') return false
  return (node.content ?? []).some(hasNodeText)
}

function renderNode(node: TiptapNode, key: string): ReactNode {
  switch (node.type) {
    case 'paragraph':
      return <p key={key}>{(node.content ?? []).map((child, index) => renderNode(child, `${key}-${index}`))}</p>
    case 'text': {
      let value: ReactNode = node.text
      for (const mark of node.marks ?? []) {
        if (mark.type === 'bold') value = <strong key={`${key}-bold`}>{value}</strong>
        if (mark.type === 'italic') value = <em key={`${key}-italic`}>{value}</em>
        if (mark.type === 'underline') value = <u key={`${key}-underline`}>{value}</u>
      }
      return <span key={key}>{value}</span>
    }
    case 'hardBreak':
      return <br key={key} />
    case 'bulletList':
      return <ul key={key}>{node.content.map((child, index) => renderNode(child, `${key}-${index}`))}</ul>
    case 'orderedList':
      return <ol key={key} start={node.attrs?.start ?? 1}>{node.content.map((child, index) => renderNode(child, `${key}-${index}`))}</ol>
    case 'listItem':
      return <li key={key}>{node.content.map((child, index) => renderNode(child, `${key}-${index}`))}</li>
  }
}

export default ResumePreview
