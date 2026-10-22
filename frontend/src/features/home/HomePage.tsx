import { useEffect, useState } from 'react'
import AuthPanel from '../auth/components/AuthPanel'
import { getAgents, type AgentDefinition } from '../chat/api/agent'
import AgentAvatar from '../../shared/components/AgentAvatar'
import './home.css'

interface HomePageProps {
  onLogin: (email: string) => void
}

export default function HomePage({ onLogin }: HomePageProps) {
  const [agents, setAgents] = useState<AgentDefinition[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    getAgents()
      .then((items) => { if (active) setAgents(items) })
      .catch(() => { if (active) setError('智能体列表暂时无法加载。') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])

  return (
    <main className="nexus-home">
      <section className="home-intro" aria-labelledby="home-title">
        <header className="home-brand">
          <img src="/brand/nexusai-icon.png" alt="" />
          <span>NEXUSAI</span>
        </header>
        <div className="home-copy">
          <p className="home-eyebrow">ONE WORKSPACE, MANY AGENTS</p>
          <h1 id="home-title">让智能体，<br />成为你的工作伙伴。</h1>
          <p className="home-description">从内容创作到研究分析，在一个工作台中调用专注不同任务的 AI 智能体。</p>
        </div>
        <section className="home-agent-section" aria-labelledby="agents-title">
          <div className="home-agent-heading">
            <h2 id="agents-title">探索智能体</h2>
            {!loading && !error && <span>{agents.length} 个智能体</span>}
          </div>
          {loading ? (
            <p className="home-agent-state" role="status">正在加载智能体…</p>
          ) : error ? (
            <p className="home-agent-state" role="alert">{error}</p>
          ) : agents.length === 0 ? (
            <p className="home-agent-state">当前没有可展示的智能体。</p>
          ) : (
            <ul className="home-agent-list">
              {agents.map((agent) => (
                <li className="home-agent-card" key={agent.agent}>
                  <AgentAvatar agent={agent.agent} />
                  <div><h3>{agent.name}</h3><p>{agent.description}</p></div>
                </li>
              ))}
            </ul>
          )}
        </section>
        <footer className="home-footer">NexusAI · 你的多智能体工作台</footer>
      </section>
      <aside className="home-auth" aria-label="账号登录与注册">
        <div className="home-auth-orb home-auth-orb-one" />
        <div className="home-auth-orb home-auth-orb-two" />
        <AuthPanel onLogin={onLogin} />
      </aside>
    </main>
  )
}
