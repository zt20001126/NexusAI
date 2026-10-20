import { lazy, Suspense, useEffect, useState } from 'react'
import ChatPage from './features/chat/ChatPage'

const ResumePage = lazy(() => import('./features/resume/ResumePage'))

/** React 应用入口，展示 NexusAI 对话页面。 */
function App() {
  const [resumeOpen, setResumeOpen] = useState(() => window.location.hash === '#/resume')

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

  return (
    <>
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
