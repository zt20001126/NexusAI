export const BEST_TIME_STORAGE_KEY = 'nexusai.xukun-run.best-time.v1'

function browserStorage() {
  try {
    return globalThis.localStorage ?? null
  } catch {
    return null
  }
}

function parseTime(value) {
  if (typeof value !== 'string' || value.trim() === '') return 0
  const milliseconds = Number(value)
  return Number.isFinite(milliseconds) && milliseconds > 0 ? Math.floor(milliseconds) : 0
}

export function readBestTime(storage = browserStorage()) {
  if (!storage) return 0

  try {
    return parseTime(storage.getItem(BEST_TIME_STORAGE_KEY))
  } catch {
    return 0
  }
}

export function saveBestTime(storage = browserStorage(), candidateMilliseconds) {
  const bestMilliseconds = readBestTime(storage)
  if (!storage || !Number.isFinite(candidateMilliseconds) || candidateMilliseconds <= bestMilliseconds) {
    return bestMilliseconds
  }

  const nextBest = Math.floor(candidateMilliseconds)
  try {
    storage.setItem(BEST_TIME_STORAGE_KEY, String(nextBest))
    return nextBest
  } catch {
    return bestMilliseconds
  }
}

export function formatRunTime(milliseconds) {
  const safeMilliseconds = Number.isFinite(milliseconds) ? Math.max(0, milliseconds) : 0
  const totalSeconds = Math.floor(safeMilliseconds / 1000)
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`
}
