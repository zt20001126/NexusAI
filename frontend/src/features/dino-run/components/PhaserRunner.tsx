import { useEffect, useRef, type MutableRefObject } from 'react'
import Phaser from 'phaser'
import RunnerScene from '../scenes/RunnerScene'
import type { RunnerCommand, RunnerSnapshot } from '../model/gameTypes'
import { RUNNER_COMMAND_EVENT, RUNNER_STATUS_EVENT } from '../model/gameTypes'
import { GAME_HEIGHT, GAME_WIDTH } from '../model/gameConfig'

interface PhaserRunnerProps {
  commandsRef: MutableRefObject<((command: RunnerCommand) => void) | null>
  onSnapshot: (snapshot: RunnerSnapshot) => void
}

/** 在 DOM 容器中创建并销毁一个 Phaser 游戏实例。 */
function PhaserRunner({ commandsRef, onSnapshot }: PhaserRunnerProps) {
  const hostRef = useRef<HTMLDivElement>(null)
  const snapshotHandlerRef = useRef(onSnapshot)
  snapshotHandlerRef.current = onSnapshot

  useEffect(() => {
    const host = hostRef.current
    if (!host) return

    const game = new Phaser.Game({
      type: Phaser.AUTO,
      parent: host,
      width: GAME_WIDTH,
      height: GAME_HEIGHT,
      backgroundColor: '#eff6ff',
      scene: [RunnerScene],
      scale: {
        mode: Phaser.Scale.FIT,
        autoCenter: Phaser.Scale.CENTER_BOTH,
      },
      physics: {
        default: 'arcade',
        arcade: { gravity: { x: 0, y: 1650 }, debug: false },
      },
      input: {
        keyboard: {
          capture: [
            Phaser.Input.Keyboard.KeyCodes.SPACE,
            Phaser.Input.Keyboard.KeyCodes.UP,
            Phaser.Input.Keyboard.KeyCodes.DOWN,
            Phaser.Input.Keyboard.KeyCodes.ESC,
          ],
        },
        mouse: false,
        touch: false,
        activePointers: 0,
      },
      render: { antialias: true, pixelArt: false },
    })

    const handleSnapshot = (snapshot: RunnerSnapshot) => snapshotHandlerRef.current(snapshot)
    game.events.on(RUNNER_STATUS_EVENT, handleSnapshot)
    commandsRef.current = (command) => game.events.emit(RUNNER_COMMAND_EVENT, command)
    game.canvas?.setAttribute('aria-label', '徐坤快跑游戏画面')

    return () => {
      commandsRef.current = null
      game.events.off(RUNNER_STATUS_EVENT, handleSnapshot)
      game.destroy(true)
    }
  }, [commandsRef])

  return <div className="dino-run-canvas" ref={hostRef} role="application" aria-label="徐坤快跑游戏画布" />
}

export default PhaserRunner
