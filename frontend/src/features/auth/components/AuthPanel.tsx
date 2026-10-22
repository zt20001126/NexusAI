import { useEffect, useState, type FormEvent } from 'react'
import {
  loginAccount,
  registerAccount,
  requestEmailCode,
  resetAccountPassword,
} from '../api/auth'
import type { AuthView } from '../model/types'

interface AuthPanelProps {
  onLogin: (email: string) => void
}

function AuthPanel({ onLogin }: AuthPanelProps) {
  const [view, setView] = useState<AuthView>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [code, setCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [cooldown, setCooldown] = useState(0)

  useEffect(() => {
    if (cooldown <= 0) return
    const timer = window.setTimeout(() => setCooldown((remaining) => remaining - 1), 1000)
    return () => window.clearTimeout(timer)
  }, [cooldown])

  function switchView(next: AuthView) {
    setView(next)
    setPassword('')
    setConfirmation('')
    setCode('')
    setError(null)
    setNotice(null)
  }

  async function sendCode() {
    setError(null)
    setNotice(null)
    setBusy(true)
    try {
      await requestEmailCode(email, view === 'register' ? 'register' : 'password_reset')
      setNotice('如果该邮箱可以进行此操作，验证码邮件将很快送达。')
      setCooldown(60)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '验证码发送失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setNotice(null)
    if ((view === 'register' || view === 'password-reset') && password !== confirmation) {
      setError('两次输入的密码不一致。')
      return
    }
    setBusy(true)
    try {
      if (view === 'login') {
        const result = await loginAccount({ email, password })
        onLogin(result.email)
      } else if (view === 'register') {
        const result = await registerAccount({
          email,
          code,
          password,
          password_confirmation: confirmation,
        })
        onLogin(result.email)
      } else {
        await resetAccountPassword({
          email,
          code,
          new_password: password,
          password_confirmation: confirmation,
        })
        switchView('login')
        setNotice('密码已更新，请使用新密码登录。')
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '操作失败，请稍后重试。')
    } finally {
      setBusy(false)
    }
  }

  const isLogin = view === 'login'
  const isRegister = view === 'register'
  const title = isLogin ? '欢迎回来' : isRegister ? '创建账号' : '重置密码'

  return (
    <section className="auth-panel" aria-labelledby="auth-panel-title">
      <div className="auth-panel-brand">
        <img src="/brand/nexusai-icon.png" alt="" />
        <span>NEXUSAI</span>
      </div>
      <h1 id="auth-panel-title">{title}</h1>
      <p className="auth-panel-subtitle">
        {isLogin ? '登录后继续使用你的智能工作台。' : isRegister ? '使用邮箱验证码完成注册。' : '验证邮箱后设置新密码。'}
      </p>

      <form className="auth-form" onSubmit={submit} noValidate>
        <label className="auth-field">
          <span>邮箱</span>
          <input
            type="email"
            autoComplete="email"
            maxLength={254}
            required
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="name@example.com"
          />
        </label>

        {!isLogin && (
          <label className="auth-field">
            <span>邮箱验证码</span>
            <span className="auth-code-row">
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                pattern="[0-9]{6}"
                required
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, '').slice(0, 6))}
                placeholder="输入 6 位验证码"
              />
              <button className="auth-code-button" type="button" disabled={busy || cooldown > 0 || !email.trim()} onClick={() => void sendCode()}>
                {cooldown > 0 ? `${cooldown}s 后重发` : '获取验证码'}
              </button>
            </span>
          </label>
        )}

        <label className="auth-field">
          <span>{view === 'password-reset' ? '新密码' : '密码'}</span>
          <input
            type="password"
            autoComplete={isLogin ? 'current-password' : 'new-password'}
            minLength={8}
            maxLength={128}
            required
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            placeholder={isLogin ? '请输入密码' : '至少 8 个字符'}
          />
        </label>

        {!isLogin && (
          <label className="auth-field">
            <span>确认密码</span>
            <input
              type="password"
              autoComplete="new-password"
              minLength={8}
              maxLength={128}
              required
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              placeholder="再次输入密码"
            />
          </label>
        )}

        {error && <p className="auth-message is-error" role="alert">{error}</p>}
        {notice && <p className="auth-message is-notice" role="status">{notice}</p>}

        <button className="auth-submit" type="submit" disabled={busy}>
          {busy ? '请稍候…' : isLogin ? '登录' : isRegister ? '注册并进入' : '更新密码'}
        </button>
      </form>

      <div className="auth-panel-links">
        {isLogin ? (
          <>
            <button type="button" onClick={() => switchView('password-reset')}>忘记密码？</button>
            <span>还没有账号？</span>
            <button type="button" onClick={() => switchView('register')}>立即注册</button>
          </>
        ) : (
          <button type="button" onClick={() => switchView('login')}>返回登录</button>
        )}
      </div>
    </section>
  )
}

export default AuthPanel
