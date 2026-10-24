import { useEffect, useRef, useState } from 'react'
import { useTopup } from '../hooks/useTopup'

interface TopupDialogProps {
  onClose: () => void
  initialTopUpId?: string
  initialCheckoutCancelled?: boolean
}

function formatCurrency(amount: number, currency: string): string {
  try {
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: currency.toUpperCase(),
      maximumFractionDigits: 0,
    }).format(amount)
  } catch {
    return String(amount) + ' ' + currency.toUpperCase()
  }
}

export function TopupDialog({
  onClose,
  initialTopUpId,
  initialCheckoutCancelled = false,
}: TopupDialogProps) {
  const topup = useTopup(initialTopUpId)
  const [showResult, setShowResult] = useState(Boolean(initialTopUpId))
  const dialogRef = useRef<HTMLDivElement>(null)
  const amountInputRef = useRef<HTMLInputElement>(null)
  const selected = topup.currencies.find((item) => item.currency === topup.selectedCurrency)
  const numericAmount = Number(topup.amount)
  const canSubmit = Boolean(
    selected
    && Number.isSafeInteger(numericAmount)
    && numericAmount >= selected.minimum_amount
    && numericAmount <= selected.maximum_amount
    && !topup.loadingOptions
    && !topup.submitting,
  )

  useEffect(() => {
    if (!initialTopUpId) amountInputRef.current?.focus()
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !dialogRef.current) return
      const controls = dialogRef.current.querySelectorAll<HTMLElement>(
        'button:not(:disabled), input:not(:disabled), select:not(:disabled)',
      )
      if (!controls.length) return
      const first = controls[0]
      const last = controls[controls.length - 1]
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [initialTopUpId, onClose])

  const resultStatus = topup.result?.status
  const isCheckoutReturn = showResult
    || topup.result?.status === 'paid'
    || topup.result?.status === 'failed'
    || topup.result?.status === 'expired'

  return (
    <div className="topup-backdrop" onMouseDown={(event) => {
      if (event.target === event.currentTarget) onClose()
    }}>
      <div
        aria-labelledby="topup-dialog-title"
        aria-modal="true"
        className="topup-dialog"
        ref={dialogRef}
        role="dialog"
      >
        <div className="topup-dialog-heading">
          <div>
            <p className="topup-eyebrow">NEXUSAI CREDITS</p>
            <h2 id="topup-dialog-title">{isCheckoutReturn ? '充值结果' : '积分充值'}</h2>
          </div>
          <button aria-label="关闭充值窗口" className="topup-close" onClick={onClose} type="button">×</button>
        </div>

        {isCheckoutReturn ? (
          <div aria-live="polite" className="topup-result" role="status">
            {!topup.result && <p>正在确认支付状态…</p>}
            {resultStatus === 'paid' && (
              <>
                <div className="topup-result-icon is-success" aria-hidden="true">✓</div>
                <h3>充值成功</h3>
                <p>已到账 {topup.result?.credits} 积分。</p>
              </>
            )}
            {resultStatus === 'pending' && (
              <>
                <div className="topup-result-icon" aria-hidden="true">…</div>
                <h3>{initialCheckoutCancelled ? '已离开支付页面' : '正在确认支付'}</h3>
                <p>{initialCheckoutCancelled
                  ? '目前没有确认到支付。若你已完成支付，积分到账后页面会更新。'
                  : '确认完成后积分会自动到账。你可以稍后刷新状态。'}</p>
                <button className="topup-secondary-button" onClick={() => { void topup.refreshStatus() }} type="button">
                  刷新状态
                </button>
                {initialCheckoutCancelled && (
                  <button className="topup-secondary-button" onClick={() => {
                    topup.startAnother()
                    setShowResult(false)
                  }} type="button">
                    再次充值
                  </button>
                )}
              </>
            )}
            {(resultStatus === 'failed' || resultStatus === 'expired') && (
              <>
                <h3>支付未完成</h3>
                <p>积分余额没有变化，你可以重新发起充值。</p>
                <button className="topup-secondary-button" onClick={() => {
                  topup.startAnother()
                  setShowResult(false)
                }} type="button">
                  再次充值
                </button>
              </>
            )}
            {topup.error && <p className="topup-error" role="alert">{topup.error}</p>}
          </div>
        ) : (
          <>
            <p className="topup-description">选择币种并输入整数金额，支付金额与获得积分按 1:1 计算。</p>
            {topup.loadingOptions ? (
              <p className="topup-loading" role="status">正在读取可用币种…</p>
            ) : topup.currencies.length === 0 ? (
              <p className="topup-empty" role="status">充值暂不可用，请稍后再试。</p>
            ) : (
              <div className="topup-form">
                <label className="topup-field">
                  <span>支付币种</span>
                  <select
                    onChange={(event) => topup.changeCurrency(event.target.value)}
                    value={topup.selectedCurrency}
                  >
                    {topup.currencies.map((item) => (
                      <option key={item.currency} value={item.currency}>
                        {item.currency.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="topup-field">
                  <span>充值金额</span>
                  <input
                    autoComplete="off"
                    inputMode="numeric"
                    max={selected?.maximum_amount}
                    min={selected?.minimum_amount}
                    onChange={(event) => topup.changeAmount(event.target.value)}
                    pattern="[0-9]*"
                    placeholder={selected ? String(selected.minimum_amount) + ' 起' : '请输入金额'}
                    ref={amountInputRef}
                    type="text"
                    value={topup.amount}
                  />
                </label>
                <p className="topup-credit-preview">
                  可获得积分 <strong>{Number.isSafeInteger(numericAmount) && numericAmount > 0 ? numericAmount : 0}</strong>
                </p>
                <div className="topup-total">
                  <span>需支付</span>
                  <strong>{selected && Number.isSafeInteger(numericAmount) && numericAmount > 0
                    ? formatCurrency(numericAmount, selected.currency)
                    : '—'}</strong>
                </div>
                {topup.error && <p className="topup-error" role="alert">{topup.error}</p>}
                <button
                  className="topup-submit"
                  disabled={!canSubmit}
                  onClick={() => { void topup.submit() }}
                  type="button"
                >
                  {topup.submitting ? '正在创建支付…' : '前往 Stripe 支付'}
                </button>
                <p className="topup-test-note">当前使用 Stripe 沙盒，不会产生真实扣款。</p>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
