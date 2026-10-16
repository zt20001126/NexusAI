export interface TimeStorage {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
}

export const BEST_TIME_STORAGE_KEY: string
export function readBestTime(storage?: TimeStorage | null): number
export function saveBestTime(storage?: TimeStorage | null, candidateMilliseconds?: number): number
export function formatRunTime(milliseconds: number): string
