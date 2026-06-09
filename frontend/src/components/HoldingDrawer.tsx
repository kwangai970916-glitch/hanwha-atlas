import { useEffect, useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import { Gavel, LineChart as LineChartIcon, X } from 'lucide-react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge, ChangePill, EmptyState, ErrorState, Skeleton, Stat } from './ui'
import { NewsFlow } from './NewsFlow'
import { fmtWonEok } from '../lib/pnlDashboardUtils'
import { cn } from '../lib/utils'

export type DrawerHolding = {
  name: string
  qty: number
  cost: number
  unit_cost: number
  price: number
  price_kind: string
  price_currency?: string | null
  price_native?: number | null
  usd_converted?: boolean | null
  value: number
  pnl: number
  pnl_pct: number
  daily_pnl?: number | null
  daily_pnl_pct?: number | null
  ytd_pnl?: number | null
  ytd_pnl_pct?: number | null
  bm: string
  bm_return_pct?: number | null
  excess_vs_bm_pct?: number | null
  acq_date: string
  matched: boolean
  live_price?: number | null
  live_change_pct?: number | null
  live_code?: string | null
  live_source?: string | null
  live_currency?: string | null
}

// ── 브랜드 토큰 → 차트 색 ────────────────────────────────────────────────
const C = {
  hanwha: 'var(--hanwha)',
  up: 'var(--up)',
  down: 'var(--down)',
  greige: 'var(--greige)',
  muted: 'var(--muted)',
  line: 'var(--line)',
  card: 'var(--card)',
  beige: 'var(--beige)',
} as const

// 작업5: 드릴다운 시리즈 API 타입
type HoldingSeriesPeriod = '1M' | '3M' | '1Y' | 'MAX'

type HoldingSeriesData = {
  name: string
  dates: string[]
  price_index: (number | null)[]
  bm_index: (number | null)[]
  bm_name: string
  period: string
  as_of: string
}

type SeriesPoint = {
  date: string
  price: number | null
  bm: number | null
}

const SERIES_PERIODS: ReadonlyArray<{ id: HoldingSeriesPeriod; label: string }> = [
  { id: '1M', label: '1M' },
  { id: '3M', label: '3M' },
  { id: '1Y', label: '1Y' },
  { id: 'MAX', label: '전체' },
]

const won = fmtWonEok
const priceText = (n: number) => Math.round(n).toLocaleString('ko-KR')
const usdText = (n: number) => `$${n.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/**
 * 우측 슬라이드인 보유종목 상세 패널.
 * 작업5: 3점 스파크라인 → 실제 recharts 종목 vs BM 시계열 차트.
 */
export function HoldingDrawer({
  holding,
  apiBase,
  onClose,
  onConvene,
}: {
  holding: DrawerHolding | null
  apiBase: string
  onClose: () => void
  /** '위원회 소집' CTA → App.goToCommittee(종목명 또는 live_code) */
  onConvene?: (ticker: string) => void
}) {
  const open = holding !== null

  // 작업5: 드릴다운 차트 상태
  const [seriesPeriod, setSeriesPeriod] = useState<HoldingSeriesPeriod>('1Y')
  const [seriesData, setSeriesData] = useState<HoldingSeriesData | null>(null)
  const [seriesState, setSeriesState] = useState<'idle' | 'loading' | 'done' | 'error'>('idle')

  // 위원회 소집 대상: 종목명 우선(백엔드가 한글명/코드 모두 해석), 없으면 코드
  const convTarget = holding ? (holding.name || holding.live_code || '') : ''
  const hasBmCompare =
    holding &&
    typeof holding.excess_vs_bm_pct === 'number' &&
    typeof holding.bm_return_pct === 'number'

  // 작업5: holding 변경 or 기간 변경 시 시리즈 fetch
  useEffect(() => {
    if (!holding) {
      setSeriesData(null)
      setSeriesState('idle')
      return
    }
    setSeriesState('loading')
    setSeriesData(null)
    const params = new URLSearchParams({ key: holding.name, period: seriesPeriod })
    fetch(`${apiBase}/api/pnl/holding-series?${params.toString()}`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: HoldingSeriesData) => {
        setSeriesData(d)
        setSeriesState('done')
      })
      .catch(() => setSeriesState('error'))
  }, [holding?.name, seriesPeriod, apiBase])

  // 기간 토글 변경 시 idle → 다시 fetch 트리거 (위 effect 에서 처리됨)
  const handlePeriodChange = (p: HoldingSeriesPeriod) => {
    setSeriesPeriod(p)
  }

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      window.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  // 작업5: 차트 데이터 변환
  const seriesChartData: SeriesPoint[] = seriesData
    ? seriesData.dates.map((d, i) => ({
        date: d,
        price: seriesData.price_index?.[i] ?? null,
        bm: seriesData.bm_index?.[i] ?? null,
      }))
    : []

  const hasSeriesData = seriesChartData.some(d => d.price != null)

  return (
    <AnimatePresence>
      {open && holding && (
        <div className="fixed inset-0 z-50 flex justify-end">
          {/* backdrop */}
          <motion.div
            className="absolute inset-0 bg-black/55 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            onClick={onClose}
          />

          {/* panel */}
          <motion.aside
            className="relative flex h-full w-full max-w-md flex-col border-l border-line bg-card shadow-card"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', stiffness: 320, damping: 34 }}
            role="dialog"
            aria-modal="true"
            aria-label={`${holding.name} 상세`}
          >
            {/* header */}
            <header className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
              <div className="min-w-0">
                <div className="mb-1 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-hanwha">
                  <span className="h-px w-5 bg-hanwha/60" />
                  보유종목 상세
                </div>
                <h2 className="truncate font-display text-lg font-bold tracking-tight text-beige">
                  {holding.name}
                </h2>
                <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                  <Badge tone={holding.price_kind === '기준가' ? 'purple' : 'blue'}>
                    {holding.price_kind || 'N/A'}
                  </Badge>
                  {holding.live_code && (
                    <Badge tone="neutral">{holding.live_code}</Badge>
                  )}
                  {!holding.matched && <Badge tone="up">가격 미매칭</Badge>}
                </div>
              </div>
              <button
                onClick={onClose}
                aria-label="닫기"
                className="grid h-8 w-8 shrink-0 place-items-center rounded-chip border border-line bg-card-2 text-muted transition-colors hover:border-hanwha hover:text-hanwha"
              >
                <X size={16} />
              </button>
            </header>

            {/* body */}
            <div className="flex-1 space-y-5 overflow-y-auto px-5 py-5">
              {/* KPI 그리드 */}
              <div className="grid grid-cols-2 gap-3">
                <Stat label="평가금액" value={won(holding.value)} />
                <Stat
                  label="누적손익"
                  value={won(holding.pnl, true)}
                  delta={holding.pnl_pct}
                />
              </div>

              {/* ── 작업5: 드릴다운 시계열 차트 (3점 스파크라인 대체) ── */}
              <div className="rounded-card border border-line bg-card-2/30 p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <div className="min-w-0">
                    <div className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                      가격 추세 (시작 100 리베이스)
                    </div>
                    {seriesData && (
                      <div className="mt-0.5 font-mono text-[10px] text-muted">
                        vs {seriesData.bm_name} · {seriesData.as_of}
                      </div>
                    )}
                  </div>
                  {/* 기간 토글 */}
                  <div className="inline-flex items-center gap-0.5 rounded-pill border border-line bg-card-2/60 p-0.5">
                    {SERIES_PERIODS.map(p => {
                      const active = p.id === seriesPeriod
                      return (
                        <button
                          key={p.id}
                          onClick={() => handlePeriodChange(p.id)}
                          className={cn(
                            'rounded-pill px-2 py-0.5 font-mono text-[10px] font-semibold transition-colors',
                            active ? 'bg-hanwha text-canvas' : 'text-muted hover:text-beige',
                          )}
                        >
                          {p.label}
                        </button>
                      )
                    })}
                  </div>
                </div>

                {/* 범례 */}
                {seriesState === 'done' && hasSeriesData && (
                  <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-[10px] text-muted">
                    <span className="inline-flex items-center gap-1.5">
                      <span className="h-1.5 w-1.5 rounded-full bg-up" />
                      {holding.name}
                    </span>
                    {seriesData && (
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="inline-block h-px w-4 rounded-full bg-down"
                          style={{ borderTop: `2px dashed var(--down)`, height: 0 }}
                        />
                        {seriesData.bm_name}
                      </span>
                    )}
                  </div>
                )}

                {/* 차트 / 상태 */}
                {seriesState === 'loading' ? (
                  <Skeleton className="h-[180px] w-full rounded-card" />
                ) : seriesState === 'error' ? (
                  <ErrorState
                    title="시계열 조회 실패"
                    message="종목 시계열 데이터를 불러오지 못했습니다."
                    onRetry={() => handlePeriodChange(seriesPeriod)}
                  />
                ) : seriesState === 'done' && !hasSeriesData ? (
                  <EmptyState
                    icon={<LineChartIcon size={18} strokeWidth={1.75} />}
                    title="데이터 없음"
                    description="이 기간에는 표시할 시계열이 없습니다."
                  />
                ) : seriesState === 'done' && hasSeriesData ? (
                  <ResponsiveContainer width="100%" height={180}>
                    <AreaChart
                      data={seriesChartData}
                      margin={{ top: 4, right: 6, left: 0, bottom: 0 }}
                    >
                      <defs>
                        <linearGradient id="drawerPortFill" x1="0" y1="0" x2="0" y2="1">
                          <stop offset="0%" stopColor={C.up} stopOpacity={0.25} />
                          <stop offset="100%" stopColor={C.up} stopOpacity={0} />
                        </linearGradient>
                      </defs>
                      <CartesianGrid
                        stroke={C.line}
                        strokeOpacity={0.35}
                        vertical={false}
                      />
                      <XAxis
                        dataKey="date"
                        tick={{
                          fill: C.muted,
                          fontSize: 9,
                          fontFamily: 'IBM Plex Mono, Pretendard, Noto Sans KR, monospace',
                        }}
                        tickLine={false}
                        axisLine={{ stroke: C.line }}
                        minTickGap={48}
                      />
                      <YAxis
                        width={40}
                        tick={{
                          fill: C.muted,
                          fontSize: 9,
                          fontFamily: 'IBM Plex Mono, Pretendard, Noto Sans KR, monospace',
                        }}
                        tickLine={false}
                        axisLine={false}
                        domain={['auto', 'auto']}
                        tickFormatter={(v: number) => v.toFixed(0)}
                      />
                      <Tooltip
                        labelStyle={{
                          color: C.greige,
                          fontFamily: 'IBM Plex Mono, Pretendard, Noto Sans KR, monospace',
                          fontSize: 10,
                        }}
                        contentStyle={{
                          background: C.card,
                          border: `1px solid ${C.line}`,
                          borderRadius: 10,
                          fontSize: 11,
                          fontFamily: 'IBM Plex Mono, Pretendard, Noto Sans KR, monospace',
                          color: C.beige,
                        }}
                        cursor={{ stroke: C.line, strokeWidth: 1 }}
                        formatter={(value: unknown, name: unknown) => {
                          const v = value as number | null
                          if (v == null) return ['—', String(name)]
                          const label =
                            name === 'bm'
                              ? (seriesData?.bm_name || 'BM')
                              : holding.name
                          return [v.toFixed(2), label]
                        }}
                      />
                      <Area
                        type="monotone"
                        dataKey="price"
                        name="price"
                        stroke={C.up}
                        strokeWidth={2}
                        fill="url(#drawerPortFill)"
                        dot={false}
                        activeDot={{ r: 3, fill: C.up }}
                        connectNulls
                      />
                      <Line
                        type="monotone"
                        dataKey="bm"
                        name="bm"
                        stroke={C.down}
                        strokeWidth={1.4}
                        strokeDasharray="4 3"
                        dot={false}
                        activeDot={{ r: 2.5, fill: C.down }}
                        connectNulls
                      />
                    </AreaChart>
                  </ResponsiveContainer>
                ) : (
                  // idle 초기 상태 (holding 없을 때)
                  <Skeleton className="h-[180px] w-full rounded-card" />
                )}
              </div>

              {/* 상세 명세 */}
              <div className="rounded-card border border-line bg-card-2/40 p-4">
                <dl className="divide-y divide-line/60 text-sm">
                  <Row label="보유수량" value={`${holding.qty.toLocaleString('ko-KR')}`} />
                  <Row
                    label={`취득단가${holding.usd_converted ? ' (USD)' : ''}`}
                    value={holding.usd_converted ? usdText(holding.unit_cost) : priceText(holding.unit_cost)}
                  />
                  <Row label="투자원금" value={won(holding.cost)} />
                  <Row
                    label={`현재가 (${holding.usd_converted ? 'USD' : holding.live_source ? 'LIVE' : holding.price_kind || 'N/A'})`}
                    value={
                      holding.usd_converted
                        ? usdText(holding.live_price != null ? holding.live_price : holding.price_native ?? 0)
                        : priceText(holding.live_price != null ? holding.live_price : holding.price)
                    }
                  />
                  <Row
                    label="수익률"
                    value={<ChangePill value={holding.pnl_pct} size="sm" />}
                  />
                  <Row
                    label="BM대비 (조정BM)"
                    value={
                      hasBmCompare ? (
                        <span className="inline-flex items-center gap-2">
                          <ChangePill value={holding.excess_vs_bm_pct!} size="sm" />
                          <span className="font-mono text-[10px] text-muted">
                            BM {holding.bm_return_pct!.toFixed(2)}%
                          </span>
                        </span>
                      ) : (
                        '—'
                      )
                    }
                  />
                  <Row label="취득일" value={holding.acq_date || '—'} />
                  <Row label="벤치마크 (BM)" value={holding.bm || '—'} />
                  {holding.live_price != null && (
                    <Row
                      label={`라이브 (${holding.live_source ?? '—'})`}
                      value={
                        <span className="inline-flex items-center gap-2">
                          <span className="font-mono tabular-nums text-beige">
                            {holding.live_currency === 'USD' || holding.usd_converted
                              ? usdText(holding.live_price)
                              : priceText(holding.live_price)}
                          </span>
                          {holding.live_change_pct != null && (
                            <ChangePill value={holding.live_change_pct} size="sm" />
                          )}
                        </span>
                      }
                    />
                  )}
                </dl>
              </div>

              {/* 위원회 소집 CTA (오렌지) — 영웅흐름 진입점 */}
              {onConvene && convTarget && (
                <motion.button
                  whileHover={{ y: -1 }}
                  whileTap={{ scale: 0.98 }}
                  onClick={() => {
                    onConvene(convTarget)
                    onClose()
                  }}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-chip bg-hanwha px-5 py-3 text-sm font-semibold text-canvas shadow-glow transition-all hover:bg-hanwha-2"
                >
                  <Gavel size={15} />
                  AI 위원회 소집
                </motion.button>
              )}

              {/* 종목 뉴스/공시 */}
              <NewsFlow
                apiBase={apiBase}
                holdings={[{ name: holding.name, code: holding.live_code ?? '' }]}
              />
            </div>
          </motion.aside>
        </div>
      )}
    </AnimatePresence>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-2.5">
      <dt className="text-xs text-muted">{label}</dt>
      <dd className="text-right font-mono tabular-nums text-beige">{value}</dd>
    </div>
  )
}

export default HoldingDrawer
