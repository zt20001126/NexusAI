import { useCallback, useEffect, useRef, useState } from 'react'
import { createTopUp, getTopUpOptions, getTopUpStatus } from '../api/topups'
import type { TopUpCurrencyOption, TopUpResult } from '../model/types'

function createRequestId(): string {
  return window.crypto.randomUUID()
}

export function useTopup(initialTopUpId?: string) {
  const [currencies, setCurrencies] = useState<TopUpCurrencyOption[]>([])
  const [selectedCurrency, setSelectedCurrency] = useState('')
  const [amount, setAmount] = useState('')
  const [result, setResult] = useState<TopUpResult | null>(null)
  const [error, setError] = useState('')
  const [loadingOptions, setLoadingOptions] = useState(true)
  const [submitting, setSubmitting] = useState(false)
  const requestIdRef = useRef(createRequestId())
  const topUpIdRef = useRef(initialTopUpId ?? '')
  const creditedTopUpIdsRef = useRef(new Set<string>())
  const [trackingTopUpId, setTrackingTopUpId] = useState(initialTopUpId ?? '')

  useEffect(() => {
    let active = true
    void getTopUpOptions()
      .then((response) => {
        if (!active) return
        setCurrencies(response.currencies)
        setSelectedCurrency(response.currencies[0]?.currency ?? '')
      })
      .catch(() => {
        if (active) setError('暂时无法读取可用的充值币种，请稍后重试。')
      })
      .finally(() => {
        if (active) setLoadingOptions(false)
      })
    return () => {
      active = false
    }
  }, [])

  const refreshStatus = useCallback(async (topUpId = topUpIdRef.current) => {
    if (!topUpId) return
    try {
      const status = await getTopUpStatus(topUpId)
      setResult(status)
      setError('')
      if (status.status === 'paid' && !creditedTopUpIdsRef.current.has(topUpId)) {
        creditedTopUpIdsRef.current.add(topUpId)
        window.dispatchEvent(new Event('nexusai:credits-changed'))
      }
    } catch {
      setError('暂时无法读取充值状态，请稍后重试。')
    }
  }, [])

  useEffect(() => {
    if (!trackingTopUpId) return
    topUpIdRef.current = trackingTopUpId
    void refreshStatus(trackingTopUpId)
    let checks = 0
    const timer = window.setInterval(() => {
      checks += 1
      if (checks > 15) {
        window.clearInterval(timer)
        return
      }
      void refreshStatus(trackingTopUpId)
    }, 2000)
    return () => window.clearInterval(timer)
  }, [trackingTopUpId, refreshStatus])

  const changeAmount = useCallback((value: string) => {
    setAmount(value)
    requestIdRef.current = createRequestId()
    setError('')
  }, [])

  const changeCurrency = useCallback((value: string) => {
    setSelectedCurrency(value)
    requestIdRef.current = createRequestId()
    setError('')
  }, [])

  const submit = useCallback(async () => {
    const numericAmount = Number(amount)
    const option = currencies.find((item) => item.currency === selectedCurrency)
    if (!option || !Number.isSafeInteger(numericAmount)
      || numericAmount < option.minimum_amount || numericAmount > option.maximum_amount) {
      setError('请输入所选币种允许范围内的正整数金额。')
      return
    }
    setSubmitting(true)
    setError('')
    try {
      const created = await createTopUp({
        currency: selectedCurrency,
        amount: numericAmount,
        request_id: requestIdRef.current,
      })
      topUpIdRef.current = created.top_up_id
      setResult(created)
      if (created.checkout_url) {
        window.location.assign(created.checkout_url)
      } else if (created.status === 'paid') {
        window.dispatchEvent(new Event('nexusai:credits-changed'))
      }
    } catch (submitError) {
      setError(submitError instanceof Error ? submitError.message : '暂时无法发起支付，请稍后重试。')
    } finally {
      setSubmitting(false)
    }
  }, [amount, currencies, selectedCurrency])

  const startAnother = useCallback(() => {
    topUpIdRef.current = ''
    setTrackingTopUpId('')
    setResult(null)
    setAmount('')
    setError('')
    requestIdRef.current = createRequestId()
  }, [])

  return {
    currencies,
    selectedCurrency,
    amount,
    result,
    error,
    loadingOptions,
    submitting,
    changeAmount,
    changeCurrency,
    submit,
    refreshStatus,
    startAnother,
  }
}
