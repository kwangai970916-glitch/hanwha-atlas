import { useEffect, useMemo, useRef, useState } from 'react'
import {
  createChart,
  ColorType,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  CrosshairMode,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData as LWCandlestickData,
  type Time,
} from 'lightweight-charts'
import { motion } from 'framer-motion'
import { CandlestickChart, Search, ChevronDown } from 'lucide-react'
import { Card, Skeleton, EmptyState, ErrorState, Badge, ChangePill } from './ui'

const PERIODS = ['1W', '1M', '3M', '1Y'] as const
type Period = (typeof PERIODS)[number]

type Candle = {
  time: string
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

type CandlesResponse = {
  candles?: Candle[]
  last_close?: number | null
  error?: string
}

type ViewState = 'loading' | 'ready' | 'empty' | 'error'

const CHART_HEIGHT = 360

/* 이동평균선 정의 */
const MA_DEFS = [
  { key: 'ma5', period: 5, color: '#f5a623', label: 'MA5' },
  { key: 'ma20', period: 20, color: '#3395ba', label: 'MA20' },
  { key: 'ma60', period: 60, color: '#a75788', label: 'MA60' },
] as const
type MaKey = (typeof MA_DEFS)[number]['key']

/* 단순이동평균 — 데이터 부족 구간은 null(차트에서 whitespace 처리) */
function sma(values: number[], period: number): (number | null)[] {
  const out: (number | null)[] = []
  let sum = 0
  for (let i = 0; i < values.length; i++) {
    sum += values[i]
    if (i >= period) sum -= values[i - period]
    out.push(i >= period - 1 ? sum / period : null)
  }
  return out
}

/* ════════════════════════════════════════════════════════
   종목/지수 검색 셀렉터 — universe 검색 + 지수 퀵칩
   선택 시 'market:select-symbol' 이벤트 → 부모가 symbol 갱신
   ════════════════════════════════════════════════════════ */
const QUICK_INDICES = [
  { code: '^KS11', name: 'KOSPI' },
  { code: '^KQ11', name: 'KOSDAQ' },
]

type UnivRow = { symbol: string; display: string; sector?: string; change?: number }

function SymbolSearch({ apiBase, label, symbol }: { apiBase: string; label: string; symbol: string }) {
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<UnivRow[]>([])
  const boxRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  useEffect(() => {
    if (!open) return
    const q = query.trim()
    const ctl = new AbortController()
    const t = window.setTimeout(() => {
      fetch(`${apiBase}/api/market/universe?q=${encodeURIComponent(q)}&limit=8`, { signal: ctl.signal })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then((d: { stocks?: UnivRow[] }) => setResults(d.stocks ?? []))
        .catch(() => { if (!ctl.signal.aborted) setResults([]) })
    }, 200)
    return () => { window.clearTimeout(t); ctl.abort() }
  }, [query, open, apiBase])

  const pick = (code: string, name: string) => {
    window.dispatchEvent(new CustomEvent('market:select-symbol', { detail: { code, name } }))
    setOpen(false)
    setQuery('')
  }

  return (
    <div ref={boxRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-2 rounded-chip border border-line/60 bg-card-2/40 px-2.5 py-1 transition-colors hover:border-hanwha/40"
      >
        <h3 className="truncate font-display text-base font-bold tracking-tight text-beige">{label}</h3>
        <Badge tone="neutral"><span className="font-mono tabular-nums">{symbol}</span></Badge>
        <ChevronDown size={13} className="text-muted" />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-2 w-72 overflow-hidden rounded-card border border-line bg-card shadow-card">
          <div className="flex items-center gap-2 border-b border-line px-3 py-2">
            <Search size={13} className="text-muted" />
            <input
              autoFocus
              value={query}
              onChange={e => setQuery(e.target.value)}
              placeholder="종목명 · 코드 검색"
              className="w-full bg-transparent font-sans text-sm text-beige outline-none placeholder:text-muted"
            />
          </div>
          <div className="flex gap-1 border-b border-line/50 px-3 py-2">
            <span className="self-center font-mono text-[10px] uppercase tracking-wide text-muted">지수</span>
            {QUICK_INDICES.map(i => (
              <button
                key={i.code}
                onClick={() => pick(i.code, i.name)}
                className="rounded-chip border border-line bg-card-2/50 px-2 py-0.5 font-mono text-[11px] font-semibold text-greige hover:border-hanwha hover:text-hanwha"
              >
                {i.name}
              </button>
            ))}
          </div>
          <div className="max-h-64 overflow-y-auto py-1">
            {results.length === 0 ? (
              <p className="px-3 py-3 text-center text-xs text-muted">
                {query ? '검색 결과 없음' : '종목명을 입력하세요'}
              </p>
            ) : (
              results.map(s => (
                <button
                  key={s.symbol}
                  onClick={() => pick(s.symbol, s.display)}
                  className="flex w-full items-center justify-between gap-2 px-3 py-1.5 text-left hover:bg-card-2/50"
                >
                  <span className="flex items-center gap-2">
                    <span className="text-sm font-medium text-beige">{s.display}</span>
                    {s.sector && <span className="font-mono text-[10px] text-muted">{s.sector}</span>}
                  </span>
                  {typeof s.change === 'number' && <ChangePill value={s.change} size="sm" />}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  )
}

/* ════════════════════════════════════════════════════════
   캔들 차트 (lightweight-charts) — 거래량 + 이동평균선 + 검색
   GET /api/market/candles/{symbol}?period=
   ════════════════════════════════════════════════════════ */
export function CandleChart({
  symbol,
  label,
  apiBase,
}: {
  symbol: string
  label: string
  apiBase: string
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)

  const [period, setPeriod] = useState<Period>('3M')
  const [data, setData] = useState<Candle[]>([])
  const [lastClose, setLastClose] = useState<number | null>(null)
  const [state, setState] = useState<ViewState>('loading')
  const [errorMsg, setErrorMsg] = useState<string | undefined>(undefined)
  const [reloadKey, setReloadKey] = useState(0)

  // 보조지표 토글
  const [showVol, setShowVol] = useState(true)
  const [maOn, setMaOn] = useState<Record<MaKey, boolean>>({ ma5: false, ma20: true, ma60: true })

  // ── 데이터 패치 ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false
    const controller = new AbortController()
    setState('loading')
    setErrorMsg(undefined)

    fetch(`${apiBase}/api/market/candles/${encodeURIComponent(symbol)}?period=${period}`, { signal: controller.signal })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json() as Promise<CandlesResponse>
      })
      .then(d => {
        if (cancelled) return
        if (d.error) {
          setErrorMsg(d.error)
          setState('error')
          return
        }
        const candles = Array.isArray(d.candles) ? d.candles : []
        setData(candles)
        setLastClose(d.last_close ?? null)
        setState(candles.length === 0 ? 'empty' : 'ready')
      })
      .catch(err => {
        if (cancelled || err?.name === 'AbortError') return
        setErrorMsg(err instanceof Error ? err.message : '네트워크 오류')
        setState('error')
      })

    return () => { cancelled = true; controller.abort() }
  }, [symbol, period, apiBase, reloadKey])

  // ── 차트 생성/갱신 ─────────────────────────────────────────────
  useEffect(() => {
    if (state !== 'ready' || !containerRef.current || data.length === 0) return

    const css = getComputedStyle(document.documentElement)
    const v = (name: string, fallback: string) => css.getPropertyValue(name).trim() || fallback
    const canvas = v('--canvas', '#241c19')
    const line = v('--line', '#5a4a43')
    const muted = v('--muted', '#a1948b')
    const greige = v('--greige', '#c9bbb0')
    const up = v('--up', '#e5484d')
    const down = v('--down', '#3395ba')

    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: 'transparent' },
        textColor: muted,
        fontFamily: "'Pretendard', 'Noto Sans KR'",
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: line, style: 0, visible: true },
        horzLines: { color: line, style: 0, visible: true },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: greige, width: 1, style: 3, labelBackgroundColor: canvas },
        horzLine: { color: greige, width: 1, style: 3, labelBackgroundColor: canvas },
      },
      rightPriceScale: { borderColor: line, scaleMargins: { top: 0.08, bottom: showVol ? 0.26 : 0.08 } },
      timeScale: { borderColor: line, timeVisible: false, fixLeftEdge: true, fixRightEdge: true },
      width: containerRef.current.clientWidth,
      height: CHART_HEIGHT,
      autoSize: false,
      handleScale: false,
      handleScroll: false,
    })

    // 거래량 히스토그램 (하단 오버레이)
    if (showVol) {
      const volSeries = chart.addSeries(HistogramSeries, {
        priceScaleId: 'vol',
        priceFormat: { type: 'volume' },
        priceLineVisible: false,
        lastValueVisible: false,
      })
      volSeries.priceScale().applyOptions({ scaleMargins: { top: 0.78, bottom: 0 } })
      volSeries.setData(
        data.map(c => ({
          time: c.time as Time,
          value: c.volume ?? 0,
          color: (c.close >= c.open ? up : down) + '55',
        })),
      )
    }

    // 이동평균선
    const closes = data.map(c => c.close)
    for (const def of MA_DEFS) {
      if (!maOn[def.key]) continue
      const ma = sma(closes, def.period)
      const points = data
        .map((c, i) => ({ time: c.time as Time, value: ma[i] }))
        .filter(p => p.value != null) as { time: Time; value: number }[]
      if (points.length < 2) continue
      const lineSeries = chart.addSeries(LineSeries, {
        color: def.color,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      })
      lineSeries.setData(points)
    }

    // 캔들 (마지막에 그려 위로 오게)
    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: up, downColor: down, borderUpColor: up, borderDownColor: down,
      wickUpColor: up, wickDownColor: down, priceLineVisible: false, lastValueVisible: true,
    })
    candleSeries.setData(data as unknown as LWCandlestickData<Time>[])
    chart.timeScale().fitContent()
    chartRef.current = chart

    const handleResize = () => {
      if (containerRef.current) {
        chart.applyOptions({ width: containerRef.current.clientWidth })
        chart.timeScale().fitContent()
      }
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
      chartRef.current = null
    }
  }, [state, data, showVol, maOn])

  // ── 헤더 요약 (KPI와 동일 소스 last_close 우선) ─────────────────
  const summary = useMemo(() => {
    if (data.length === 0) return null
    const first = data[0]
    const close = lastClose ?? data[data.length - 1].close
    const change = close - first.open
    const pct = first.open !== 0 ? (change / first.open) * 100 : 0
    return { close, pct }
  }, [data, lastClose])

  const periodTabs = (
    <div className="flex items-center gap-0.5 rounded-pill border border-line bg-card-2/50 p-0.5">
      {PERIODS.map(p => {
        const active = period === p
        return (
          <button
            key={p}
            type="button"
            onClick={() => setPeriod(p)}
            className={`relative rounded-pill px-2.5 py-1 font-mono text-[11px] font-semibold tabular-nums tracking-wide transition-colors ${active ? 'text-canvas' : 'text-muted hover:text-beige'}`}
          >
            {active && (
              <motion.span
                layoutId={`candle-period-${symbol}`}
                transition={{ type: 'spring', stiffness: 360, damping: 30 }}
                className="absolute inset-0 -z-0 rounded-pill bg-hanwha"
              />
            )}
            <span className="relative z-10">{p}</span>
          </button>
        )
      })}
    </div>
  )

  // 보조지표 토글 칩
  const indicatorChips = (
    <div className="flex flex-wrap items-center gap-1">
      {MA_DEFS.map(def => (
        <button
          key={def.key}
          type="button"
          onClick={() => setMaOn(s => ({ ...s, [def.key]: !s[def.key] }))}
          className={`rounded-chip border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors ${
            maOn[def.key] ? 'border-transparent text-canvas' : 'border-line text-muted hover:text-beige'
          }`}
          style={maOn[def.key] ? { background: def.color } : undefined}
        >
          {def.label}
        </button>
      ))}
      <button
        type="button"
        onClick={() => setShowVol(s => !s)}
        className={`rounded-chip border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors ${
          showVol ? 'border-hanwha/50 bg-hanwha/15 text-hanwha' : 'border-line text-muted hover:text-beige'
        }`}
      >
        VOL
      </button>
    </div>
  )

  return (
    <Card noPadding hover>
      <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-4 pb-3">
        <div className="min-w-0">
          <div className="mb-1.5 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-hanwha">
            <CandlestickChart size={13} strokeWidth={2} />
            캔들 차트
          </div>
          <SymbolSearch apiBase={apiBase} label={label} symbol={symbol} />
        </div>

        <div className="flex flex-col items-end gap-2">
          {periodTabs}
          {state === 'ready' && summary && (
            <div className="flex items-center gap-2">
              <span className="font-mono text-sm font-bold tabular-nums text-beige">
                {summary.close.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}
              </span>
              <ChangePill value={summary.pct} percent size="sm" />
            </div>
          )}
          {indicatorChips}
        </div>
      </div>

      <div className="px-5 pb-5">
        <div className="relative" style={{ minHeight: CHART_HEIGHT }}>
          {state === 'loading' && (
            <div className="absolute inset-0 flex flex-col gap-2">
              <Skeleton className="h-full w-full rounded-card" />
            </div>
          )}
          {state === 'error' && (
            <ErrorState
              message={errorMsg ? `캔들 데이터를 불러오지 못했습니다 (${errorMsg})` : '캔들 데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.'}
              onRetry={() => setReloadKey(k => k + 1)}
            />
          )}
          {state === 'empty' && (
            <EmptyState
              icon={<CandlestickChart size={20} strokeWidth={1.75} />}
              title="표시할 캔들이 없습니다"
              description={`${label}의 ${period} 구간 시세 데이터가 없습니다.`}
            />
          )}
          <div
            ref={containerRef}
            className={state === 'ready' ? 'block' : 'invisible h-0 overflow-hidden'}
          />
        </div>
      </div>
    </Card>
  )
}

export default CandleChart
