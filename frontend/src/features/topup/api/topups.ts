import { requestJson } from '../../../shared/api/http'
import type { TopUpOptions, TopUpResult } from '../model/types'

export function getTopUpOptions(): Promise<TopUpOptions> {
  return requestJson('/api/credits/top-up-options')
}

export function createTopUp(input: {
  currency: string
  amount: number
  request_id: string
}): Promise<TopUpResult> {
  return requestJson('/api/credits/top-ups', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function getTopUpStatus(topUpId: string): Promise<TopUpResult> {
  return requestJson('/api/credits/top-ups/' + encodeURIComponent(topUpId))
}
