import { useEffect, useState } from 'react'
import { getListingTaskResult } from '../api/agent'
import type { ListingOutputVersion } from '../api/agent'
import type { TaskResultSummary } from '../api/conversations'

interface ListingResultCardProps {
  result: TaskResultSummary
}

/** 读取并展示任务结果 JSON 中的三个 Listing 版本。 */
function ListingResultCard({ result }: ListingResultCardProps) {
  const [versions, setVersions] = useState<ListingOutputVersion[]>([])
  const [selectedVersion, setSelectedVersion] = useState(1)
  const [loading, setLoading] = useState(result.generation_status === 'succeeded')
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (result.generation_status !== 'succeeded') {
      setLoading(false)
      setVersions([])
      return
    }
    let current = true
    setLoading(true)
    setError(null)
    getListingTaskResult(result.task_result_id)
      .then((detail) => {
        if (!current) return
        setVersions(detail.result_data.versions)
      })
      .catch((requestError: unknown) => {
        if (current) {
          setError(requestError instanceof Error ? requestError.message : '读取 Listing 结果失败。')
        }
      })
      .finally(() => {
        if (current) setLoading(false)
      })
    return () => { current = false }
  }, [result.generation_status, result.task_result_id])

  if (result.generation_status !== 'succeeded') {
    return <p role="status">{listingStatusText(result.generation_status)}</p>
  }
  if (loading) return <p role="status">正在读取 Listing 结果…</p>
  if (error) return <p role="alert">Listing 结果暂时无法读取：{error}</p>
  const activeVersion = versions.find((version) => version.version === selectedVersion)
  if (!activeVersion) return <p role="status">没有可展示的 Listing 版本。</p>

  return (
    <div className="listing-result">
      <div className="listing-version-tabs" role="tablist" aria-label="选择 Listing 版本">
        {versions.map((version) => (
          <button
            key={version.version}
            type="button"
            role="tab"
            aria-selected={selectedVersion === version.version}
            className={selectedVersion === version.version ? 'is-selected' : ''}
            onClick={() => setSelectedVersion(version.version)}
          >
            版本 {version.version}
          </button>
        ))}
      </div>
      <section className="listing-version-content" aria-label={'Listing 版本 ' + activeVersion.version}>
        <h3>标题</h3>
        <p>{activeVersion.title}</p>
        <h3>卖点</h3>
        <ul>{activeVersion.selling_points.map((point) => <li key={point}>{point}</li>)}</ul>
        <h3>详情描述</h3>
        <p className="listing-description">{activeVersion.description}</p>
        <h3>关键词</h3>
        <div className="listing-keywords">
          {activeVersion.keywords.map((keyword) => <span key={keyword}>{keyword}</span>)}
        </div>
        <h3>商品属性</h3>
        <dl className="listing-attributes">
          {Object.entries(activeVersion.product_attributes).map(([name, value]) => (
            <div key={name}><dt>{name}</dt><dd>{value}</dd></div>
          ))}
        </dl>
      </section>
    </div>
  )
}

function listingStatusText(status: string): string {
  if (status === 'awaiting_input') return '等待商品信息核实…'
  if (status === 'failed') return 'Listing 生成未完成，请检查错误提示后重试。'
  if (status === 'cancelled') return 'Listing 生成已取消。'
  return '正在生成 Listing…'
}

export default ListingResultCard
