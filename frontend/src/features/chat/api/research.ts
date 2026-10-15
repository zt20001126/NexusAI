/** 科研文献检索结果详情 API 和数据类型。 */

import { requestJson } from '../../../shared/api/http'

export interface ResearchPaper {
  id: string
  title: string
  authors: string[]
  year: number | null
  language: string | null
  publication_date: string | null
  venue: string | null
  abstract: string | null
  doi: string | null
  citation_count: number
  paper_url: string
  pdf_url: string | null
  source: string
}

export interface ResearchTaskResult {
  task_result_id: string
  agent_id: string
  result_type: 'research_search'
  generation_status: string
  result_data: {
    schema_version: number
    status: 'success' | 'partial' | 'no_results' | 'failed'
    query: string
    message: string
    returned_count: number
    papers: ResearchPaper[]
    filters: Record<string, unknown>
    source: string
    retrieved_at: string
  }
}

export function getResearchTaskResult(taskResultId: string): Promise<ResearchTaskResult> {
  return requestJson('/api/task-results/' + encodeURIComponent(taskResultId))
}
