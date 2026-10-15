import { useEffect, useState } from 'react'
import { getResearchTaskResult } from '../api/research'
import type { ResearchPaper } from '../api/research'
import type { TaskResultSummary } from '../api/conversations'

interface ResearchResultCardProps {
  result: TaskResultSummary
}

/** 读取 JSONB 中的论文列表，展示 OpenAlex 返回的可核验字段。 */
function ResearchResultCard({ result }: ResearchResultCardProps) {
  const [papers, setPapers] = useState<ResearchPaper[]>([])
  const [status, setStatus] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [loading, setLoading] = useState(result.generation_status === 'succeeded')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (result.generation_status !== 'succeeded') {
      setLoading(false)
      setPapers([])
      return
    }
    let current = true
    setLoading(true)
    setError(null)
    getResearchTaskResult(result.task_result_id)
      .then((detail) => {
        if (!current) return
        setPapers(detail.result_data.papers)
        setStatus(detail.result_data.status)
        setMessage(detail.result_data.message)
      })
      .catch((requestError: unknown) => {
        if (current) {
          setError(requestError instanceof Error ? requestError.message : '读取论文结果失败。')
        }
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => { current = false }
  }, [result.generation_status, result.task_result_id])

  if (result.generation_status !== 'succeeded') {
    return <p role="status">{generationStatusText(result.generation_status)}</p>
  }
  if (loading) return <p role="status">正在读取论文结果…</p>
  if (error) return <p role="alert">论文结果暂时无法读取：{error}</p>

  return (
    <section className="research-result" aria-label="科研文献检索结果">
      {message && <p className="research-result-message" role="status">{message}</p>}
      {status === 'failed' && <p className="research-result-empty">本次未能从 OpenAlex 取得可用结果。</p>}
      {status === 'no_results' && <p className="research-result-empty">可以尝试调整主题词或年份范围。</p>}
      {papers.map((paper) => (
        <article className="research-paper" key={paper.doi || paper.id}>
          <h3>
            <a href={paper.paper_url} target="_blank" rel="noreferrer">{paper.title}</a>
          </h3>
          <p className="research-paper-meta">
            {[paper.authors.join(', '), paper.year, paper.venue, '引用 ' + paper.citation_count]
              .filter((value) => value !== null && value !== undefined && value !== '')
              .join(' · ')}
          </p>
          {paper.abstract && <p className="research-paper-abstract">{paper.abstract}</p>}
          <div className="research-paper-links">
            {paper.doi && (
              <a
                href={'https://doi.org/' + encodeURI(paper.doi)}
                target="_blank"
                rel="noreferrer"
              >
                DOI: {paper.doi}
              </a>
            )}
            {paper.pdf_url && <a href={paper.pdf_url} target="_blank" rel="noreferrer">开放 PDF</a>}
          </div>
        </article>
      ))}
      {status === 'success' && papers.length === 0 && (
        <p className="research-result-empty">暂时没有可展示的论文。</p>
      )}
    </section>
  )
}

function generationStatusText(status: string): string {
  if (status === 'failed') return '科研文献检索未完成，请稍后重试。'
  if (status === 'cancelled') return '科研文献检索已取消。'
  return '正在检索科研文献…'
}

export default ResearchResultCard
