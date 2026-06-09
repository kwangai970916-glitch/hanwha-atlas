export type PnlBasis = 'daily' | 'ytd' | 'cumulative'
export type HoldingSortKey = 'value' | 'pnl'
export type SortDir = 'asc' | 'desc'

export type SortState = {
  key: HoldingSortKey
  dir: SortDir
} | null

export type HoldingLike = {
  name?: string
  qty: number
  price: number
  value: number
  daily_value?: number | null
  pnl: number
  pnl_pct: number
  daily_pnl?: number | null
  daily_pnl_pct?: number | null
  ytd_pnl?: number | null
  ytd_pnl_pct?: number | null
  usd_converted?: boolean | null
  price_native?: number | null
  live_price?: number | null
  live_change_pct?: number | null
}

export type HoldingDisplayMetrics = {
  value: number
  pnl: number
  pnl_pct: number
}

export function fmtWonEok(n: number, signed = false): string {
  const sign = signed && n > 0 ? '+' : n < 0 ? '-' : ''
  const absEok = Math.abs(n) / 100_000_000
  return `${sign}${absEok.toLocaleString('ko-KR', {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}억`
}

export function getHoldingDisplayMetrics<T extends HoldingLike>(holding: T, basis: PnlBasis): HoldingDisplayMetrics {
  if (basis === 'daily' && typeof holding.daily_pnl === 'number') {
    return {
      value: holding.daily_value ?? holding.value ?? 0,
      pnl: holding.daily_pnl,
      pnl_pct: holding.daily_pnl_pct ?? 0,
    }
  }
  if (basis === 'daily' && typeof holding.live_price === 'number' && holding.live_price > 0) {
    const isUsdConverted = Boolean(holding.usd_converted && holding.price_native && holding.price)
    const fx = isUsdConverted ? holding.price / Number(holding.price_native) : 1
    const basePrice = isUsdConverted ? Number(holding.price_native) : holding.price
    const liveValue = holding.live_price * holding.qty * fx
    const pnl = (holding.live_price - basePrice) * holding.qty * fx
    const pnlPct =
      typeof holding.live_change_pct === 'number'
        ? holding.live_change_pct
        : basePrice > 0
          ? (holding.live_price / basePrice - 1) * 100
          : 0
    return { value: Math.round(liveValue), pnl: Math.round(pnl), pnl_pct: Math.round(pnlPct * 100) / 100 }
  }
  if (basis === 'daily') {
    return { value: holding.value || 0, pnl: 0, pnl_pct: 0 }
  }
  if (basis === 'ytd') {
    return {
      value: holding.value || 0,
      pnl: holding.ytd_pnl ?? 0,
      pnl_pct: holding.ytd_pnl_pct ?? 0,
    }
  }
  return { value: holding.value || 0, pnl: holding.pnl || 0, pnl_pct: holding.pnl_pct || 0 }
}

export function sortHoldings<T extends HoldingLike>(holdings: readonly T[], sort: SortState, basis: PnlBasis): T[] {
  if (!sort) return [...holdings]
  const direction = sort.dir === 'asc' ? 1 : -1
  return [...holdings].sort((a, b) => {
    const av = getHoldingDisplayMetrics(a, basis)[sort.key]
    const bv = getHoldingDisplayMetrics(b, basis)[sort.key]
    if (av === bv) return String(a.name || '').localeCompare(String(b.name || ''), 'ko-KR')
    return (av - bv) * direction
  })
}

export function getHoldingsSubtotal<T extends HoldingLike>(holdings: readonly T[], basis: PnlBasis): HoldingDisplayMetrics {
  const total = holdings.reduce(
    (acc, h) => {
      const m = getHoldingDisplayMetrics(h, basis)
      acc.value += m.value
      acc.pnl += m.pnl
      return acc
    },
    { value: 0, pnl: 0 },
  )
  const cost = total.value - total.pnl
  const pnlPct = cost ? (total.pnl / cost) * 100 : 0
  return {
    value: Math.round(total.value),
    pnl: Math.round(total.pnl),
    pnl_pct: Math.round(pnlPct * 100) / 100,
  }
}

export function nextSortState(current: SortState, key: HoldingSortKey): SortState {
  if (!current || current.key !== key) return { key, dir: 'desc' }
  return { key, dir: current.dir === 'desc' ? 'asc' : 'desc' }
}
