import { describe, expect, it } from 'vitest'
import { fmtWonEok, getHoldingDisplayMetrics, getHoldingsSubtotal, sortHoldings } from './pnlDashboardUtils'

const base = [
  { name: 'A', qty: 10, value: 300_000_000, pnl: 20_000_000, pnl_pct: 7, price: 30_000, live_price: 31_000, live_change_pct: 3.33 },
  { name: 'B', qty: 10, value: 100_000_000, pnl: -5_000_000, pnl_pct: -5, price: 10_000, live_price: 9_500, live_change_pct: -5 },
  { name: 'C', qty: 10, value: 200_000_000, pnl: 10_000_000, pnl_pct: 5, price: 20_000 },
]

describe('fmtWonEok', () => {
  it('formats won amounts in eok units with sign', () => {
    expect(fmtWonEok(1_234_000_000)).toBe('12.3억')
    expect(fmtWonEok(120_000_000, true)).toBe('+1.2억')
    expect(fmtWonEok(-50_000_000, true)).toBe('-0.5억')
    expect(fmtWonEok(0)).toBe('0.0억')
  })
})

describe('getHoldingDisplayMetrics', () => {
  it('uses cumulative value and pnl for cumulative basis', () => {
    expect(getHoldingDisplayMetrics(base[0], 'cumulative')).toMatchObject({
      value: 300_000_000,
      pnl: 20_000_000,
      pnl_pct: 7,
    })
  })

  it('uses live intraday value and pnl for daily basis when live price exists', () => {
    expect(getHoldingDisplayMetrics(base[0], 'daily')).toMatchObject({
      value: 310_000,
      pnl: 10_000,
      pnl_pct: 3.33,
    })
  })
})

describe('sortHoldings', () => {
  it('sorts by displayed value ascending and descending', () => {
    expect(sortHoldings(base, { key: 'value', dir: 'asc' }, 'cumulative').map(h => h.name)).toEqual(['B', 'C', 'A'])
    expect(sortHoldings(base, { key: 'value', dir: 'desc' }, 'cumulative').map(h => h.name)).toEqual(['A', 'C', 'B'])
  })

  it('sorts by displayed pnl ascending and descending', () => {
    expect(sortHoldings(base, { key: 'pnl', dir: 'asc' }, 'cumulative').map(h => h.name)).toEqual(['B', 'C', 'A'])
    expect(sortHoldings(base, { key: 'pnl', dir: 'desc' }, 'cumulative').map(h => h.name)).toEqual(['A', 'C', 'B'])
  })
})


describe('getHoldingsSubtotal', () => {
  it('sums displayed value and pnl and derives pnl pct', () => {
    expect(getHoldingsSubtotal(base, 'cumulative')).toEqual({
      value: 600_000_000,
      pnl: 25_000_000,
      pnl_pct: 4.35,
    })
  })
})

describe('daily basis currency and missing live data', () => {
  it('does not fall back to cumulative pnl when daily live price is missing', () => {
    expect(getHoldingDisplayMetrics(base[2], 'daily')).toMatchObject({
      value: 200_000_000,
      pnl: 0,
      pnl_pct: 0,
    })
  })

  it('converts USD live prices to KRW using the Excel converted/native price ratio', () => {
    const grab = {
      name: '그랩홀딩스',
      qty: 100,
      price: 14_000,
      price_native: 10,
      usd_converted: true,
      live_price: 11,
      value: 1_400_000,
      pnl: 400_000,
      pnl_pct: 40,
    }
    expect(getHoldingDisplayMetrics(grab, 'daily')).toMatchObject({
      value: 1_540_000,
      pnl: 140_000,
      pnl_pct: 10,
    })
  })
})
