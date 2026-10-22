export interface AuthSession {
  authenticated: boolean
  email: string | null
}

export interface AuthAccountResult {
  email: string
}

export type AuthView = 'login' | 'register' | 'password-reset'
