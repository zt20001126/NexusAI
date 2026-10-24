import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import ChatPage from './features/chat/ChatPage'
import HomePage from './features/home/HomePage'
import { useAuth } from './features/auth/hooks/useAuth'
import { TopupDialog } from './features/topup/components/TopupDialog'

const ResumePage = lazy(() => import('./features/resume/ResumePage'))

function getTopUpIdFromHash(): string | null {
  const hash = window.location.hash
  if (!hash.startsWith('#/topup?')) return null
  return new URLSearchParams(hash.slice(hash.indexOf('?') + 1)).get('top_up_id')
}

function didCancelTopUpFromHash(): boolean {
  const hash = window.location.hash
  if (!hash.startsWith('#/topup?')) return false
  return new URLSearchParams(hash.slice(hash.indexOf('?') + 1)).get('checkout') === 'cancelled'
}

/** React 应用入口，负责账号会话守卫与工作台路由。 */
function App() {
  const [resumeOpen, setResumeOpen] = useState(() => window.location.hash === '#/resume')
  const [topUpReturnId, setTopUpReturnId] = useState(getTopUpIdFromHash)
  const [topUpCancelled, setTopUpCancelled] = useState(didCancelTopUpFromHash)
  const [topUpOpen, setTopUpOpen] = useState(false)
  const topUpTriggerRef = useRef<HTMLButtonElement>(null)
  const auth = useAuth()

  useEffect(() => {
    function syncLocation() {
      setResumeOpen(window.location.hash === '#/resume')
      setTopUpReturnId(getTopUpIdFromHash())
      setTopUpCancelled(didCancelTopUpFromHash())
      setTopUpOpen(false)
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

  const closeTopUp = useCallback(() => {
    setTopUpOpen(false)
    setTopUpReturnId(null)
    setTopUpCancelled(false)
    if (getTopUpIdFromHash()) window.location.hash = '/market'
    window.requestAnimationFrame(() => topUpTriggerRef.current?.focus())
  }, [])

  if (auth.loading) return <main className="resume-app-shell" role="status">正在准备 NexusAI…</main>
  if (!auth.session.authenticated) return <HomePage onLogin={auth.acceptLogin} />

  return (
    <>
      <div className="auth-account-bar">
        <span className="auth-account-credits" aria-label="当前积分">
          {auth.session.credits === null ? '积分同步中' : `${auth.session.credits} 积分`}
        </span>
        <button
          className="auth-account-topup"
          onClick={() => setTopUpOpen(true)}
          ref={topUpTriggerRef}
          type="button"
        >
          充值
        </button>
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
      {(topUpOpen || topUpReturnId) && (
        <TopupDialog
          initialCheckoutCancelled={topUpCancelled}
          initialTopUpId={topUpReturnId ?? undefined}
          onClose={closeTopUp}
        />
      )}
    </>
  )
}

export default App
