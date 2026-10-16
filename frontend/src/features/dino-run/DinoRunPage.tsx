import { useCallback, useEffect, useRef, useState } from 'react'
import PhaserRunner from './components/PhaserRunner'
import { formatRunTime, readBestTime, saveBestTime } from './model/record.mjs'
import type { RunnerCommand, RunnerSnapshot, RunnerStatus } from './model/gameTypes'

interface DinoRunPageProps {
  onReturnToMarket: () => void
}

function DinoRunPage({ onReturnToMarket }: DinoRunPageProps) {
  const commandsRef = useRef<((command: RunnerCommand) => void) | null>(null)
  const [status, setStatus] = useState<RunnerStatus>('ready')
  const [elapsedMs, setElapsedMs] = useState(0)
  const [bestTimeMs, setBestTimeMs] = useState(() => readBestTime())

  const handleSnapshot = useCallback((snapshot: RunnerSnapshot) => {
    setStatus(snapshot.status)
    setElapsedMs(snapshot.elapsedMs)
    if (snapshot.status === 'gameover') {
      setBestTimeMs(saveBestTime(undefined, snapshot.elapsedMs))
    }
  }, [])

  useEffect(() => {
    function pauseWhenHidden() {
      if (document.visibilityState === 'hidden' && status === 'running') {
        commandsRef.current?.('pause')
      }
    }

    document.addEventListener('visibilitychange', pauseWhenHidden)
    return () => document.removeEventListener('visibilitychange', pauseWhenHidden)
  }, [status])

  function startGame() {
    commandsRef.current?.('start')
  }

  function restartGame() {
    commandsRef.current?.('restart')
  }

  function togglePause() {
    commandsRef.current?.(status === 'paused' ? 'resume' : 'pause')
  }

  return (
    <section className="dino-run-page" aria-labelledby="dino-run-title">
      <header className="dino-run-page-header">
        <div>
          <p className="dino-run-eyebrow">NEXUSAI · MINI GAME</p>
          <h1 id="dino-run-title">徐坤快跑</h1>
          <p className="dino-run-subtitle">躲开障碍，坚持得更久，刷新你的最长记录。</p>
        </div>
        <button className="dino-run-return" type="button" onClick={onReturnToMarket}>
          ← 返回市场
        </button>
      </header>

      <div className="dino-run-panel">
        <div className="dino-run-toolbar">
          <div className="dino-run-stat" aria-live="polite">
            <span>本局坚持</span>
            <strong>{formatRunTime(elapsedMs)}</strong>
          </div>
          <div className="dino-run-stat dino-run-record" aria-live="polite">
            <span>最长记录</span>
            <strong>{formatRunTime(bestTimeMs)}</strong>
          </div>
          <button
            className="dino-run-pause"
            type="button"
            onClick={togglePause}
            disabled={status !== 'running' && status !== 'paused'}
          >
            {status === 'paused' ? '继续' : '暂停'}
          </button>
        </div>

        <div className="dino-run-stage">
          <PhaserRunner commandsRef={commandsRef} onSnapshot={handleSnapshot} />
          {status !== 'running' && (
            <div className="dino-run-overlay" role="group" aria-label="游戏控制">
              {status === 'ready' && (
                <>
                  <span className="dino-run-overlay-kicker">READY?</span>
                  <h2>准备好了吗？</h2>
                  <p>空格键或 ↑ 跳跃，↓ 下蹲。碰到障碍，本局就结束。</p>
                  <button className="dino-run-primary" type="button" onClick={startGame}>开始游戏</button>
                </>
              )}
              {status === 'paused' && (
                <>
                  <span className="dino-run-overlay-kicker">PAUSED</span>
                  <h2>游戏已暂停</h2>
                  <p>按 P 或 Esc 也可以继续。</p>
                  <div className="dino-run-overlay-actions">
                    <button className="dino-run-primary" type="button" onClick={togglePause}>继续游戏</button>
                    <button className="dino-run-secondary" type="button" onClick={restartGame}>重新开始</button>
                  </div>
                </>
              )}
              {status === 'gameover' && (
                <>
                  <span className="dino-run-overlay-kicker">GAME OVER</span>
                  <h2>本局结束</h2>
                  <p>坚持了 <strong>{formatRunTime(elapsedMs)}</strong>，最长记录是 <strong>{formatRunTime(bestTimeMs)}</strong>。</p>
                  <button className="dino-run-primary" type="button" onClick={restartGame}>再跑一次</button>
                </>
              )}
            </div>
          )}
        </div>

        <footer className="dino-run-controls">
          <span><kbd>空格</kbd> / <kbd>↑</kbd> 跳跃</span>
          <span><kbd>↓</kbd> 下蹲</span>
          <span><kbd>P</kbd> / <kbd>Esc</kbd> 暂停</span>
        </footer>
      </div>
    </section>
  )
}

export default DinoRunPage
