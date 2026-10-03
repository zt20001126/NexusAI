/** 统一处理前端到 FastAPI 的 JSON 请求、错误响应和 SSE 请求。 */

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

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

export interface AgentEvent {
  event_id: string
  event_type: string
  conversation_id: string
  run_id: string
  sequence: number
  timestamp: string
  data: Record<string, unknown>
}

function parseEventBlock(block: string): AgentEvent | null {
  const dataLines = block
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())

  if (dataLines.length === 0) return null
  return JSON.parse(dataLines.join('\n')) as AgentEvent
}

/** 通过 fetch 发送 POST 请求并逐条读取后端命名 SSE 事件。 */
export async function streamAgentEvents(
  path: string,
  payload: unknown,
  onEvent: (event: AgentEvent) => void,
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
        const event = parseEventBlock(block)
        if (event) onEvent(event)
      }
      if (done) break
    }

    const finalEvent = parseEventBlock(buffer)
    if (finalEvent) onEvent(finalEvent)
  } finally {
    reader.releaseLock()
  }
}
