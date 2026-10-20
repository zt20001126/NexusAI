/** 提供前端共享的 JSON 请求、错误处理与 SSE 传输能力。 */

import { parseSseBlock } from './sseParser.mjs'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

interface ApiEnvelope<T> {
  success: boolean
  data?: T
  code?: string
  message?: string
  detail?: string | Array<{ msg?: string }>
}

function readApiErrorMessage(body: ApiEnvelope<unknown> | null, status: number): string {
  if (body?.message) return body.message
  if (typeof body?.detail === 'string') return body.detail
  if (Array.isArray(body?.detail) && body.detail[0]?.msg) return body.detail[0].msg
  return `请求失败（HTTP ${status}）`
}

function isTerminalStreamEventType(eventType: unknown): boolean {
  return eventType === 'run.terminal' || eventType === 'question.required'
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
    throw new Error(readApiErrorMessage(body, response.status))
  }

  return body.data
}

/** 上传原始文件内容，并读取项目统一 JSON 成功响应。 */
export async function requestBinary<T>(
  path: string,
  body: Blob,
  fileName: string,
): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': body.type || 'application/octet-stream',
    },
    body,
  })
  const envelope = (await response.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!response.ok || !envelope?.success || envelope.data === undefined) {
    throw new Error(`${readApiErrorMessage(envelope, response.status)}（${fileName}）`)
  }
  return envelope.data
}

/** 通过 multipart/form-data 上传文件，浏览器自行生成 Content-Type 边界。 */
export async function requestFormData<T>(path: string, body: FormData): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { Accept: 'application/json' },
    body,
  })
  const envelope = (await response.json().catch(() => null)) as ApiEnvelope<T> | null
  if (!response.ok || !envelope?.success || envelope.data === undefined) {
    throw new Error(readApiErrorMessage(envelope, response.status))
  }
  return envelope.data
}

export interface StreamEventOptions {
  signal?: AbortSignal
  onEventId?: (eventId: string) => void
  onRun?: (conversationId: string, runId: string) => void
  onExpired?: () => string | null | void | Promise<string | null | void>
  run?: { conversationId: string; runId: string; after?: string | null }
}

class RetryableStreamError extends Error {}

/** 提交或监听 SSE；连接中断后携带最后游标重连共享 listen 接口。 */
export async function streamEvents<T>(
  path: string,
  payload: unknown,
  onEvent: (event: T, eventId?: string) => void,
  options: StreamEventOptions = {},
): Promise<void> {
  let conversationId = options.run?.conversationId ?? null
  let runId = options.run?.runId ?? null
  let lastEventId = options.run?.after ?? null
  let reconnectDelay = 500
  let historyLoaded = false

  while (!options.signal?.aborted) {
    const isListening = Boolean(conversationId && runId)
    let requestPath = path
    const headers: Record<string, string> = { Accept: 'text/event-stream' }
    let init: RequestInit
    if (isListening) {
      const query = new URLSearchParams({ run_id: runId as string })
      if (lastEventId) query.set('after', lastEventId)
      requestPath = `/api/agents/listen/${encodeURIComponent(conversationId as string)}?${query.toString()}`
      if (lastEventId) headers['Last-Event-ID'] = lastEventId
      if (historyLoaded) headers['X-Agent-History-Loaded'] = 'true'
      init = { method: 'GET', headers, signal: options.signal }
    } else {
      headers['Content-Type'] = 'application/json'
      init = {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
        signal: options.signal,
      }
    }

    try {
      const response = await fetch(`${API_BASE_URL}${requestPath}`, init)
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as ApiEnvelope<unknown> | null
        if (response.status === 410 && isListening) {
          const restartCursor = await options.onExpired?.()
          if (restartCursor && conversationId && runId) {
            lastEventId = restartCursor
            historyLoaded = true
            reconnectDelay = 500
            continue
          }
          return
        }
        if (response.status >= 500 && isListening) {
          throw new RetryableStreamError(readApiErrorMessage(body, response.status))
        }
        if (response.status >= 500) throw new Error(readApiErrorMessage(body, response.status))
        throw new Error(readApiErrorMessage(body, response.status))
      }

      if (!isListening) {
        conversationId = response.headers.get('X-Conversation-ID')
        runId = response.headers.get('X-Run-ID')
        if (conversationId && runId) options.onRun?.(conversationId, runId)
      }
      if (!response.body) throw new Error('浏览器无法读取服务器的流式响应')

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''
      let terminal = false
      let streamClosed = false
      try {
        while (true) {
          const { done, value } = await reader.read()
          buffer += decoder.decode(value, { stream: !done })
          const blocks = buffer.split(/\r?\n\r?\n/)
          buffer = blocks.pop() ?? ''
          for (const block of blocks) {
            const frame = parseSseBlock<T>(block)
            if (frame.id !== null) {
              lastEventId = frame.id
              options.onEventId?.(frame.id)
            }
            if (frame.data !== null) {
              onEvent(frame.data, frame.id ?? undefined)
              const eventType = (frame.data as { event_type?: unknown }).event_type
              if (isTerminalStreamEventType(eventType)) terminal = true
            }
          }
          if (done) streamClosed = true
          if (done || terminal || options.signal?.aborted) break
        }
        const finalFrame = buffer ? parseSseBlock<T>(buffer) : null
        if (finalFrame?.id !== null && finalFrame?.id !== undefined) {
          lastEventId = finalFrame.id
          options.onEventId?.(finalFrame.id)
        }
        if (finalFrame?.data !== null && finalFrame?.data !== undefined) {
          onEvent(finalFrame.data, finalFrame.id ?? undefined)
          const eventType = (finalFrame.data as { event_type?: unknown }).event_type
          if (isTerminalStreamEventType(eventType)) terminal = true
        }
      } finally {
        reader.releaseLock()
      }
      if (streamClosed && !terminal && conversationId && runId && !options.signal?.aborted) {
        throw new RetryableStreamError('SSE 连接已关闭，正在恢复监听')
      }
      return
    } catch (error) {
      if (options.signal?.aborted) return
      if (error instanceof RetryableStreamError) {
        await new Promise<void>((resolve) => window.setTimeout(resolve, reconnectDelay))
        reconnectDelay = Math.min(reconnectDelay * 2, 15_000)
        continue
      }
      if (error instanceof Error && error.message !== 'Failed to fetch'
        && !(error instanceof TypeError)) {
        throw error
      }
      await new Promise<void>((resolve) => window.setTimeout(resolve, reconnectDelay))
      reconnectDelay = Math.min(reconnectDelay * 2, 15_000)
    }
  }
}
