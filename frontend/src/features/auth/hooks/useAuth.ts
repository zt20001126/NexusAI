import { useCallback, useEffect, useState } from 'react'
import { getAuthSession, logoutAccount } from '../api/auth'
import type { AuthSession } from '../model/types'

const SIGNED_OUT: AuthSession = { authenticated: false, email: null }

export function useAuth() {
  const [session, setSession] = useState<AuthSession>(SIGNED_OUT)
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    setLoading(true)
    try {
      setSession(await getAuthSession())
    } catch {
      setSession(SIGNED_OUT)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void refresh()
  }, [refresh])

  useEffect(() => {
    function handleUnauthenticated() {
      setSession(SIGNED_OUT)
    }
    window.addEventListener('nexusai:unauthenticated', handleUnauthenticated)
    return () => window.removeEventListener('nexusai:unauthenticated', handleUnauthenticated)
  }, [])

  const acceptLogin = useCallback((email: string) => {
    setSession({ authenticated: true, email })
    setLoading(false)
  }, [])

  const logout = useCallback(async () => {
    try {
      await logoutAccount()
    } finally {
      setSession(SIGNED_OUT)
    }
  }, [])

  return { session, loading, acceptLogin, logout, refresh }
}
