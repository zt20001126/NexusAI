export interface ParsedSseFrame<T> {
  id: string | null
  event: string | null
  data: T | null
}

export function parseSseBlock<T = unknown>(block: string): ParsedSseFrame<T>
