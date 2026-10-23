import { lazy, Suspense, useEffect, useState } from 'react'
import ChatPage from './features/chat/ChatPage'
import HomePage from './features/home/HomePage'
import { useAuth } from './features/auth/hooks/useAuth'

const ResumePage = lazy(() => import('./features/resume/ResumePage'))

/** React 应用入口，负责账号会话守卫与工作台路由。 */
function App() {
  const [resumeOpen, setResumeOpen] = useState(() => window.location.hash === '#/resume')
  const auth = useAuth()

  useEffect(() => {
    function syncLocation() {
      setResumeOpen(window.location.hash === '#/resume')
    }
    window.addEventListener('hashchange', syncLocation)
    return () => window.removeEventListener('hashchange', syncLocation)
  }, [])

  function openResume() {
    window.location.hash = '/resume'
  }

  function returnToMarket() {
    window.location.hash = '/market'
  }

  if (auth.loading) return <main className="resume-app-shell" role="status">正在准备 NexusAI…</main>
  if (!auth.session.authenticated) return <HomePage onLogin={auth.acceptLogin} />

  return (
    <>
      <div className="auth-account-bar">
        <span className="auth-account-credits" aria-label="当前积分">
          {auth.session.credits === null ? '积分同步中' : `${auth.session.credits} 积分`}
        </span>
        <span>{auth.session.email}</span>
        <button type="button" onClick={() => { void auth.logout(); window.location.hash = '/market' }}>退出登录</button>
      </div>
      <div hidden={resumeOpen}>
        <ChatPage onOpenResume={openResume} />
      </div>
      {resumeOpen && (
        <Suspense fallback={<main className="resume-app-shell" role="status">正在打开简历助手…</main>}>
          <ResumePage onBack={returnToMarket} />
        </Suspense>
      )}
    </>
  )
}

export default App
