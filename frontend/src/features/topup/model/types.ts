export interface TopUpCurrencyOption {
  currency: string
  minimum_amount: number
  maximum_amount: number
}

export interface TopUpOptions {
  currencies: TopUpCurrencyOption[]
}

export interface TopUpResult {
  top_up_id: string
  currency: string
  amount: number
  credits: number
  status: 'pending' | 'paid' | 'failed' | 'expired'
  checkout_url: string | null
}
