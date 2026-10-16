export type RunnerStatus = 'ready' | 'running' | 'paused' | 'gameover'

export type RunnerCommand = 'start' | 'pause' | 'resume' | 'restart'

export interface RunnerSnapshot {
  status: RunnerStatus
  elapsedMs: number
}

export const RUNNER_STATUS_EVENT = 'xukun-run:status'
export const RUNNER_COMMAND_EVENT = 'xukun-run:command'
