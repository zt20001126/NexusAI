import { useCallback, useEffect, useRef, useState } from 'react'
import { getAuthSession, logoutAccount } from '../api/auth'
import type { AuthSession } from '../model/types'

const SIGNED_OUT: AuthSession = { authenticated: false, email: null, credits: null }

export function useAuth() {
  const [session, setSession] = useState<AuthSession>(SIGNED_OUT)
  const [loading, setLoading] = useState(true)
  const hasLoadedSessionRef = useRef(false)

  const refresh = useCallback(async () => {
    if (!hasLoadedSessionRef.current) setLoading(true)
    try {
      setSession(await getAuthSession())
    } catch {
      setSession((current) => current.authenticated ? { ...current, credits: null } : SIGNED_OUT)
    } finally {
      hasLoadedSessionRef.current = true
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
    function handleCreditsChanged() {
      void refresh()
    }
    function handleWindowFocus() {
      void refresh()
    }
    window.addEventListener('nexusai:unauthenticated', handleUnauthenticated)
    window.addEventListener('nexusai:credits-changed', handleCreditsChanged)
    window.addEventListener('focus', handleWindowFocus)
    return () => {
      window.removeEventListener('nexusai:unauthenticated', handleUnauthenticated)
      window.removeEventListener('nexusai:credits-changed', handleCreditsChanged)
      window.removeEventListener('focus', handleWindowFocus)
    }
  }, [refresh])

  const acceptLogin = useCallback((email: string) => {
    setSession({ authenticated: true, email, credits: null })
    hasLoadedSessionRef.current = true
    setLoading(false)
    void refresh()
  }, [refresh])

  const logout = useCallback(async () => {
    try {
      await logoutAccount()
    } finally {
      setSession(SIGNED_OUT)
    }
  }, [])

  return { session, loading, acceptLogin, logout, refresh }
}
