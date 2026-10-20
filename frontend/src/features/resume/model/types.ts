export type ResumeSection = 'basic' | 'education' | 'skills' | 'work' | 'projects' | 'style'

export interface BasicInfo {
  name: string
  phone: string
  email: string
  intended_position: string
  age: number | null
  work_experience_years: number | null
  photo_id: string | null
}

export interface EducationItem {
  id: string
  school: string
  major: string
  degree: string
  start_month: string
  end_month: string
}

export interface TiptapMark {
  type: 'bold' | 'italic' | 'underline'
}

export interface TiptapText {
  type: 'text'
  text: string
  marks?: TiptapMark[]
}

export interface TiptapHardBreak {
  type: 'hardBreak'
}

export interface TiptapParagraph {
  type: 'paragraph'
  content?: Array<TiptapText | TiptapHardBreak>
}

export interface TiptapListItem {
  type: 'listItem'
  content: Array<TiptapParagraph | TiptapBulletList | TiptapOrderedList>
}

export interface TiptapBulletList {
  type: 'bulletList'
  content: TiptapListItem[]
}

export interface TiptapOrderedList {
  type: 'orderedList'
  attrs?: { start?: number }
  content: TiptapListItem[]
}

export interface TiptapDocument {
  type: 'doc'
  content: Array<TiptapParagraph | TiptapBulletList | TiptapOrderedList>
}

export type TiptapNode = TiptapParagraph | TiptapText | TiptapHardBreak | TiptapBulletList | TiptapOrderedList | TiptapListItem

export interface WorkItem {
  id: string
  company: string
  position: string
  start_month: string
  end_month: string
  content: TiptapDocument
}

export interface ProjectItem {
  id: string
  name: string
  role: string
  technology_stack: string
  start_month: string
  end_month: string
  content: TiptapDocument
}

export interface ResumeContent {
  basic_info: BasicInfo
  educations: EducationItem[]
  skills: TiptapDocument
  works: WorkItem[]
  projects: ProjectItem[]
}

export interface PageMargin {
  top: number
  right: number
  bottom: number
  left: number
}

export interface ResumeStyleConfig {
  font_family: 'wenquanyi_zenhei' | 'arphic_ukai'
  font_size_pt: number
  line_height: number
  paragraph_spacing_pt: number
  section_spacing_pt: number
  page_margin_mm: PageMargin
  heading_color: string
  divider_color: string
  divider_width_pt: number
}

export interface ResumeResponse {
  exists: boolean
  content: ResumeContent
  style_config: ResumeStyleConfig
  created_at: string | null
  updated_at: string | null
}

export interface ResumeDraft {
  content: ResumeContent
  style_config: ResumeStyleConfig
}

export const DEFAULT_RESUME_CONTENT: ResumeContent = {
  basic_info: {
    name: '',
    phone: '',
    email: '',
    intended_position: '',
    age: null,
    work_experience_years: null,
    photo_id: null,
  },
  educations: [],
  skills: { type: 'doc', content: [{ type: 'paragraph', content: [] }] },
  works: [],
  projects: [],
}

export const DEFAULT_RESUME_STYLE: ResumeStyleConfig = {
  font_family: 'wenquanyi_zenhei',
  font_size_pt: 10,
  line_height: 1.4,
  paragraph_spacing_pt: 4,
  section_spacing_pt: 12,
  page_margin_mm: { top: 14, right: 14, bottom: 14, left: 14 },
  heading_color: '#1677FF',
  divider_color: '#1677FF',
  divider_width_pt: 1,
}

export function createEmptyTiptapDocument(): TiptapDocument {
  return { type: 'doc', content: [{ type: 'paragraph', content: [] }] }
}

export function createDefaultDraft(): ResumeDraft {
  return {
    content: structuredClone(DEFAULT_RESUME_CONTENT),
    style_config: structuredClone(DEFAULT_RESUME_STYLE),
  }
}
