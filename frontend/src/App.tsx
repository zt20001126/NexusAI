function App() {
  return (
    <main className="app-shell">
      <header className="app-header">
        <strong>NexusAI</strong>
        <a href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
          FastAPI 文档
        </a>
      </header>
      <section className="welcome-card">
        <p className="eyebrow">REACT · TYPESCRIPT · VITE</p>
        <h1>前端开发环境已就绪</h1>
        <p>React 应用位于 frontend/，FastAPI 服务位于 backend/。</p>
        <a className="api-link" href="http://127.0.0.1:8000/docs" target="_blank" rel="noreferrer">
          打开后端 API 文档 <span aria-hidden="true">↗</span>
        </a>
      </section>
      <footer>Monorepo workspace · backend + frontend</footer>
    </main>
  )
}

export default App
