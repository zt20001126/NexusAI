import { requestJson } from '../../../shared/api/http'
import type { AuthAccountResult, AuthSession } from '../model/types'

export type EmailCodePurpose = 'register' | 'password_reset'

export function getAuthSession(): Promise<AuthSession> {
  return requestJson('/api/auth/session')
}

export function requestEmailCode(email: string, purpose: EmailCodePurpose): Promise<{ requested: boolean }> {
  return requestJson('/api/auth/email-codes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, purpose }),
  })
}

export function registerAccount(input: {
  email: string
  code: string
  password: string
  password_confirmation: string
}): Promise<AuthAccountResult> {
  return requestJson('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function loginAccount(input: { email: string; password: string }): Promise<AuthAccountResult> {
  return requestJson('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function resetAccountPassword(input: {
  email: string
  code: string
  new_password: string
  password_confirmation: string
}): Promise<{ password_reset: boolean }> {
  return requestJson('/api/auth/password-reset', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
}

export function logoutAccount(): Promise<{ logged_out: boolean }> {
  return requestJson('/api/auth/logout', { method: 'POST' })
}
