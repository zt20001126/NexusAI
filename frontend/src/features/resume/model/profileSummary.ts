import type { BasicInfo, EducationItem } from './types'

export interface ResumeProfileSummary {
  positionItems: string[]
  contactItems: string[]
}

export function createResumeProfileSummary(
  basicInfo: BasicInfo,
  educations: readonly Pick<EducationItem, 'degree'>[],
): ResumeProfileSummary {
  const positionItems = [basicInfo.intended_position.trim()]
  if (basicInfo.work_experience_years !== null) {
    positionItems.push(`${basicInfo.work_experience_years}年工作经验`)
  }

  const firstFilledDegree = educations.find((item) => item.degree.trim())?.degree.trim()
  const contactItems = [basicInfo.phone.trim(), basicInfo.email.trim()]
  if (basicInfo.age !== null) contactItems.push(`${basicInfo.age}岁`)
  if (firstFilledDegree) contactItems.push(firstFilledDegree)

  return {
    positionItems: positionItems.filter(Boolean),
    contactItems: contactItems.filter(Boolean),
  }
}
