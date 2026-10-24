export interface AuthSession {
  authenticated: boolean
  email: string | null
  credits: number | null
}

export interface AuthAccountResult {
  email: string
}

export type AuthView = 'login' | 'register' | 'password-reset'
