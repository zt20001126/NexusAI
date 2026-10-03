/** 提供前端共享的 JSON 请求、错误处理与 SSE 传输能力。 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

/** 返回后端 FastAPI Swagger UI 地址。 */
export function getApiDocsUrl(): string {
  const docsBaseUrl = API_BASE_URL || (import.meta.env.DEV ? 'http://127.0.0.1:8000' : '')
  return `${docsBaseUrl.replace(/\/+$/, '')}/docs`
}

interface ApiEnvelope<T> {
  success: boolean
  data?: T
  code?: string
  message?: string
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...init?.headers,
    },
  })
  const body = (await response.json().catch(() => null)) as ApiEnvelope<T> | null

  if (!response.ok || !body?.success || body.data === undefined) {
    throw new Error(body?.message ?? `请求失败（HTTP ${response.status}）`)
  }

  return body.data
}

function parseEventBlock<T>(block: string): T | null {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())

  if (dataLines.length === 0) return null
  return JSON.parse(dataLines.join('\n')) as T
}

/** 通过 fetch 发送 POST 请求并逐条读取 SSE 数据事件。 */
export async function streamEvents<T>(
  path: string,
  payload: unknown,
  onEvent: (event: T) => void,
  signal?: AbortSignal,
): Promise<void> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'text/event-stream',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
    signal,
  })

  if (!response.ok) {
    const body = (await response.json().catch(() => null)) as ApiEnvelope<unknown> | null
    throw new Error(body?.message ?? `请求失败（HTTP ${response.status}）`)
  }
  if (!response.body) throw new Error('浏览器无法读取服务器的流式响应')

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  try {
    while (true) {
      const { done, value } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const blocks = buffer.split(/\r?\n\r?\n/)
      buffer = blocks.pop() ?? ''
      for (const block of blocks) {
        const event = parseEventBlock<T>(block)
        if (event) onEvent(event)
      }
      if (done) break
    }

    const finalEvent = parseEventBlock<T>(buffer)
    if (finalEvent) onEvent(finalEvent)
  } finally {
    reader.releaseLock()
  }
}
