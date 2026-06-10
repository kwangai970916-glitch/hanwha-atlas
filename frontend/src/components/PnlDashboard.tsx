import { useCallback, useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { AlertTriangle, ArrowUpRight, ChevronRight, Info, LineChart as LineChartIcon, Receipt } from 'lucide-react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  Badge,
  Card,
  ChangePill,
  EmptyState,
  ErrorState,
  SectionHeader,
  Skeleton,
  Sparkline,
} from './ui'
import { cn } from '../lib/utils'
import { NewsFlow } from './NewsFlow'
import { HoldingDrawer, type DrawerHolding } from './HoldingDrawer'
import {
  fmtWonEok,
  getHoldingDisplayMetrics,
  getHoldingsSubtotal,
  nextSortState,
  sortHoldings,
  type HoldingSortKey,
  type PnlBasis,
  type SortState,
} from '../lib/pnlDashboardUtils'

// ── 브랜드 토큰 → 차트 색 (하드코딩 hex 금지: CSS 변수만) ───────────────
const C = {
  hanwha: 'var(--hanwha)',
  up: 'var(--up)',
  down: 'var(--down)',
  blue: 'var(--blue)',
  greige: 'var(--greige)',
  muted: 'var(--muted)',
  line: 'var(--line)',
  card: 'var(--card)',
  beige: 'var(--beige)',
} as const

type Holding = DrawerHolding & {
  contribution_pct?: number | null
}

type Transaction = {
  name: string
  date: string
  qty: string
  realized_pr?: number | null
  realized_tr?: number | null
}

// Task C: enriched trade from /api/pnl/trades
type Trade = {
  name: string
  sell_date: string
  qty: string
  avg_buy_price: number | null
  avg_sell_price: number | null
  holding_days: number | null
  pnl: number | null
  return_pct: number | null
  cum_pnl: number
}

type TradesData = {
  trades: Trade[]
  total: number
  limit: number
  offset: number
  sort: string
  order: string
  sells_col_fallback?: boolean
}

type PnlSummary = {
  total_daily_pnl?: number | null
  total_daily_pnl_pct?: number | null
  realized_pnl_total?: number | null
}

type PnlData = {
  holdings: Holding[]
  total_cost?: number
  total_value: number
  total_pnl: number
  total_pnl_pct?: number
  transactions?: Transaction[]
  unmatched?: string[]
  as_of?: string
  // P2-2: 시세 기준일(거래일) vs 서버 조회 시각 분리
  price_as_of?: string | null
  live_price_as_of?: string | null
  fetched_at?: string | null
  error?: string
  // 작업2: 일간 손익 요약
  total_daily_pnl?: number | null
  total_daily_pnl_pct?: number | null
  // 작업3: 실현손익 누계
  realized_pnl_total?: number | null
  summary?: PnlSummary
}

type RiskData = {
  ann_return: number
  ann_vol: number
  mdd: number
  beta: number
  tracking_error: number
  info_ratio: number
  excess_return: number
  bm_ann_return: number
  sharpe?: number | null
  calmar?: number | null
  bm_name: string
  bm_resolved: boolean
  coverage_pct: number
  default_bm_used: boolean
  n_obs: number
  period: string
  methodology: string
}

type AttributionGroup = {
  group: string
  weight_pct: number
  market_value: number
  pnl: number
  pnl_contribution_pct: number
  avg_return_pct: number
  holdings_count: number
}

type AttributionData = {
  groups: AttributionGroup[]
  total_market_value: number
  total_pnl: number
  as_of?: string
  error?: string
}

type RollingRiskData = {
  dates: string[]
  beta: (number | null)[]
  ir: (number | null)[]
  window: number
  as_of?: string | null
  error?: string
}

type CurveData = {
  dates: string[]
  portfolio_value: number[]
  portfolio_index: (number | null)[]
  cum_pnl: (number | null)[]
  portfolio_cost: number
  bm_index: (number | null)[]
  bm_name: string
  bm_resolved: boolean
  coverage_pct: number
  days: number
  period: string
  as_of?: string
  // 작업3: 실현+미실현 통합 시리즈
  realized_cum?: (number | null)[]
  total_incl_realized?: (number | null)[]
  realized_pnl_total?: number | null
}

type Period = '3M' | '1Y' | 'MAX'
type CurveMode = 'cumulative' | 'daily'
// 작업3: 곡선 표시 모드
type CurveDisplay = 'eval' | 'total' | 'realized'

const PERIODS: ReadonlyArray<{ id: Period; label: string }> = [
  { id: '3M', label: '3M' },
  { id: '1Y', label: '1Y' },
  { id: 'MAX', label: '전체' },
]

const fmtWon = fmtWonEok
const fmtUsd = (v: number | null | undefined) =>
  v == null || Number.isNaN(v)
    ? '—'
    : `$${v.toLocaleString('ko-KR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** 소수(0.1193) → 퍼센트 문자열(11.93%). signed=true면 부호 표기. */
const fmtPct = (v: number | null | undefined, digits = 2, signed = false) => {
  if (v == null || Number.isNaN(v)) return '—'
  const p = v * 100
  const sign = signed && p > 0 ? '+' : ''
  return `${sign}${p.toFixed(digits)}%`
}

/** ISO/날짜 문자열 → HH:mm (조회 시각 표기용). 실패 시 '—'. */
const fmtHhmm = (iso: string | null | undefined) => {
  if (!iso) return '—'
  const m = iso.match(/T(\d{2}):(\d{2})/)
  if (m) return `${m[1]}:${m[2]}`
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

/** 시세 기준일(YYYY-MM-DD)이 stale(주말 또는 장 시작 전)인지 판정. */
const isStalePriceDay = (priceAsOf: string | null | undefined): boolean => {
  if (!priceAsOf) return false
  const m = priceAsOf.match(/(\d{4})-(\d{2})-(\d{2})/)
  if (!m) return false
  const priceDate = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  if (Number.isNaN(priceDate.getTime())) return false
  const dow = priceDate.getDay()
  // 주말 기준일이면 stale (직전 영업일 시세)
  if (dow === 0 || dow === 6) return true
  // 시세 기준일이 오늘이 아니고(=과거일) 지나면 stale (장 마감/장전 전일 시세)
  const today = new Date()
  const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`
  return priceAsOf.slice(0, 10) !== todayKey
}

const stagger = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06 } },
}
const item = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 240, damping: 26 } },
}

export function PnlDashboard({
  apiBase,
  goToCommittee,
}: {
  apiBase: string
  goToCommittee?: (ticker: string) => void
}) {
  const [data, setData] = useState<PnlData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [selected, setSelected] = useState<Holding | null>(null)

  // 위험지표(/api/pnl/risk) + 손익곡선(/api/pnl/curve)
  const [risk, setRisk] = useState<RiskData | null>(null)
  const [curve, setCurve] = useState<CurveData | null>(null)
  const [period, setPeriod] = useState<Period>('1Y')
  const [curveMode, setCurveMode] = useState<CurveMode>('cumulative')
  const [curveDisplay, setCurveDisplay] = useState<CurveDisplay>('eval')
  const [curveState, setCurveState] = useState<'loading' | 'done' | 'error'>('loading')
  const [pnlBasis, setPnlBasis] = useState<PnlBasis>('daily')
  const [holdingSort, setHoldingSort] = useState<SortState>(null)
  const [attribution, setAttribution] = useState<AttributionData | null>(null)
  const [rollingRisk, setRollingRisk] = useState<RollingRiskData | null>(null)
  // Task C: paginated trades
  const [tradesData, setTradesData] = useState<TradesData | null>(null)
  const [tradesOffset, setTradesOffset] = useState(0)
  const [tradesLoading, setTradesLoading] = useState(false)
  const TRADES_LIMIT = 20

  const load = useCallback(
    (initial = false) => {
      if (initial) {
        setLoading(true)
        setError(false)
      }
      return fetch(`${apiBase}/api/pnl`)
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          return r.json()
        })
        .then((d: PnlData) => {
          setData(d)
          setError(false)
        })
        .catch(() => {
          if (initial) setError(true)
        })
        .finally(() => {
          if (initial) setLoading(false)
        })
    },
    [apiBase],
  )

  // 위험지표: 기간 변경/주기 갱신 시 재조회(베스트에포트, 실패해도 본문은 유지)
  const loadRisk = useCallback(
    (p: Period) => {
      const q = p === 'MAX' ? '' : p
      return fetch(`${apiBase}/api/pnl/risk?period=${q}`)
        .then(r => (r.ok ? r.json() : null))
        .then((d: RiskData | null) => {
          if (d && typeof d.ann_return === 'number') setRisk(d)
        })
        .catch(() => {})
    },
    [apiBase],
  )

  // 손익곡선: 기간별 재조회(로딩/에러 상태 보유)
  const loadCurve = useCallback(
    (p: Period) => {
      setCurveState('loading')
      const q = p === 'MAX' ? '' : p
      return fetch(`${apiBase}/api/pnl/curve?period=${q}`)
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          return r.json()
        })
        .then((d: CurveData) => {
          setCurve(d)
          setCurveState('done')
        })
        .catch(() => setCurveState('error'))
    },
    [apiBase],
  )

  // 자산군 기여 분석 (초기 1회 + 30초 갱신)
  const loadAttribution = useCallback(() => {
    return fetch(`${apiBase}/api/pnl/attribution`)
      .then(r => (r.ok ? r.json() : null))
      .then((d: AttributionData | null) => {
        if (d && Array.isArray(d.groups)) setAttribution(d)
      })
      .catch(() => {})
  }, [apiBase])

  // 롤링 위험지표 (초기 1회 로드)
  const loadRollingRisk = useCallback(() => {
    return fetch(`${apiBase}/api/pnl/rolling-risk`)
      .then(r => (r.ok ? r.json() : null))
      .then((d: RollingRiskData | null) => {
        if (d && Array.isArray(d.dates)) setRollingRisk(d)
      })
      .catch(() => {})
  }, [apiBase])

  // Task C: 매도내역 paginated trades
  const loadTrades = useCallback(
    (off: number, append = false) => {
      setTradesLoading(true)
      return fetch(`${apiBase}/api/pnl/trades?limit=${TRADES_LIMIT}&offset=${off}&sort=date&order=desc`)
        .then(r => (r.ok ? r.json() : null))
        .then((d: TradesData | null) => {
          if (!d || !Array.isArray(d.trades)) return
          setTradesData(prev =>
            append && prev
              ? { ...d, trades: [...prev.trades, ...d.trades] }
              : d,
          )
          setTradesOffset(off)
        })
        .catch(() => {})
        .finally(() => setTradesLoading(false))
    },
    [apiBase, TRADES_LIMIT],
  )

  useEffect(() => {
    load(true)
    loadAttribution()
    loadRollingRisk()
    loadTrades(0, false)
    const t = setInterval(() => { load(false); loadAttribution() }, 30_000)
    return () => clearInterval(t)
  }, [load, loadAttribution, loadRollingRisk, loadTrades])

  // 기간 토글 → 위험지표 + 곡선 동시 재조회
  useEffect(() => {
    loadRisk(period)
    loadCurve(period)
  }, [period, loadRisk, loadCurve])

  // 차트 포인트: 누적=포트지수(100기준) vs BM지수 / 일간=누적손익(원)
  const chartData = useMemo(() => {
    if (!curve) return []
    const { dates, portfolio_index, bm_index, cum_pnl, realized_cum, total_incl_realized } = curve
    return dates.map((d, i) => ({
      date: d,
      port: portfolio_index?.[i] ?? null,
      bm: bm_index?.[i] ?? null,
      cum: cum_pnl?.[i] ?? null,
      realizedCum: realized_cum?.[i] ?? null,
      totalInclRealized: total_incl_realized?.[i] ?? null,
    }))
  }, [curve])

  // ---- 로딩 스켈레톤 ----
  if (loading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-40 w-full rounded-card" />
        <Card title="보유종목">
          <div className="space-y-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-9 w-full" />
            ))}
          </div>
        </Card>
      </div>
    )
  }

  // ---- 에러 상태 ----
  if (error || !data) {
    return (
      <ErrorState
        title="손익 데이터를 불러오지 못했습니다"
        message="서버 응답이 없습니다. 네트워크 또는 백엔드 상태를 확인한 뒤 다시 시도하세요."
        onRetry={() => load(true)}
      />
    )
  }

  // ---- 백엔드 명시 에러 ----
  if (data.error) {
    return (
      <ErrorState
        title="손익 집계 불가"
        message={data.error}
        onRetry={() => load(true)}
      />
    )
  }

  const holdings = data.holdings ?? []
  const displayedHoldings = sortHoldings(holdings, holdingSort, pnlBasis)
  const holdingsSubtotal = getHoldingsSubtotal(displayedHoldings, pnlBasis)
  const totalPos = data.total_pnl >= 0
  const totalPctPos = (data.total_pnl_pct ?? 0) >= 0
  const unmatched = data.unmatched ?? []
  const asOf = data.as_of ? data.as_of.replace('T', ' ').slice(0, 19) : '—'

  // P2-2: 시세 신선도 — 기준일(거래일) vs 조회 시각 분리, 주말/장전이면 stale 경고
  const effectivePriceAsOf = data.live_price_as_of || data.price_as_of
  const priceAsOf = effectivePriceAsOf ? effectivePriceAsOf.slice(0, 10) : '—'
  const fetchedHhmm = fmtHhmm(data.fetched_at)
  const priceStale = isStalePriceDay(effectivePriceAsOf)

  // 비중(%) 산정용 분모: 총평가액(없으면 보유 평가액 합)
  const totalValForWeight =
    displayedHoldings.reduce((s, h) => s + getHoldingDisplayMetrics(h, pnlBasis).value, 0) ||
    data.total_value ||
    1
  // 수익률 막대 정규화용 최대 절대 수익률
  const maxAbsPct = displayedHoldings.reduce(
    (m, h) => Math.max(m, Math.abs(getHoldingDisplayMetrics(h, pnlBasis).pnl_pct || 0)),
    1,
  )
  const subtotalPos = holdingsSubtotal.pnl >= 0
  const handleHoldingSort = (key: HoldingSortKey) => {
    setHoldingSort(current => nextSortState(current, key))
  }

  // 작업2: 일간 손익 — summary 또는 루트 필드에서 읽기
  const totalDailyPnl =
    data.total_daily_pnl ?? data.summary?.total_daily_pnl ?? null
  const totalDailyPnlPct =
    data.total_daily_pnl_pct ?? data.summary?.total_daily_pnl_pct ?? null

  // 작업3: 실현손익 누계 — curve 또는 루트/summary 에서 읽기
  const realizedPnlTotal =
    curve?.realized_pnl_total ?? data.realized_pnl_total ?? data.summary?.realized_pnl_total ?? null

  return (
    <motion.div
      className="space-y-6"
      variants={stagger}
      initial="hidden"
      animate="show"
    >
      {/* ============ HERO: 오늘의 운용 요약 ============ */}
      <motion.div variants={item}>
        <div className="relative overflow-hidden rounded-card border border-line bg-card bg-warm-radial shadow-card">
          {/* 오렌지 포인트 라인 */}
          <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-70" />
          <div className="relative p-6">
            <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-hanwha">
              <span className="h-px w-6 bg-hanwha/60" />
              오늘의 운용 요약
              <span className="ml-auto inline-flex items-center gap-1.5 text-[10px] tracking-[0.06em] text-muted">
                <span className="h-1.5 w-1.5 animate-pulse-soft rounded-full bg-hanwha" />
                {asOf}
              </span>
            </div>

            {/* ───── 시세 신선도 라벨 (기준일 vs 조회시각, 2단·작은 글씨) ───── */}
            <div
              className={cn(
                'mt-3 inline-flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 font-mono text-[10.5px] leading-tight',
                priceStale ? 'text-down' : 'text-muted',
              )}
            >
              <span className={cn('font-semibold', priceStale ? 'text-down' : 'text-greige')}>
                시세 {priceAsOf} 기준
              </span>
              <span className="text-muted">·</span>
              <span>{fetchedHhmm} 조회</span>
              {priceStale && (
                <span className="ml-1 inline-flex items-center gap-1 text-down">
                  <AlertTriangle size={11} className="shrink-0" />
                  장 마감·주말 기준 (직전 영업일 시세)
                </span>
              )}
            </div>

            <div className="mt-5 grid grid-cols-1 gap-6 md:grid-cols-12">
              {/* 총평가액 (큰수치) */}
              <div className="md:col-span-5">
                <div className="font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">
                  총 평가금액
                </div>
                <div className="mt-1.5 font-mono text-4xl font-bold tabular-nums leading-none text-beige">
                  {fmtWon(data.total_value)}
                </div>
                <div className="mt-3 flex flex-wrap items-center gap-2">
                  <span
                    className={cn(
                      'font-mono text-base font-bold tabular-nums',
                      totalPos ? 'text-up' : 'text-down',
                    )}
                  >
                    {fmtWon(data.total_pnl, true)}
                  </span>
                  {typeof data.total_pnl_pct === 'number' && (
                    <ChangePill value={data.total_pnl_pct} />
                  )}
                </div>

                {/* 작업2: 일간 손익 배너 */}
                {totalDailyPnl != null && (
                  <div className="mt-3 inline-flex items-center gap-2 rounded-chip border border-line/60 bg-card-2/50 px-3 py-1.5">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
                      오늘
                    </span>
                    <span
                      className={cn(
                        'font-mono text-sm font-bold tabular-nums',
                        totalDailyPnl >= 0 ? 'text-up' : 'text-down',
                      )}
                    >
                      {fmtWon(totalDailyPnl, true)}
                    </span>
                    {totalDailyPnlPct != null && (
                      <ChangePill value={totalDailyPnlPct} size="sm" />
                    )}
                  </div>
                )}

                {/* 작업3: 실현손익 누계 표기 */}
                {realizedPnlTotal != null && (
                  <div className="mt-2 inline-flex items-center gap-2 rounded-chip border border-line/60 bg-card-2/50 px-3 py-1.5">
                    <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
                      실현손익 누계
                    </span>
                    <span
                      className={cn(
                        'font-mono text-sm font-bold tabular-nums',
                        realizedPnlTotal >= 0 ? 'text-up' : 'text-down',
                      )}
                    >
                      {fmtWon(realizedPnlTotal, true)}
                    </span>
                  </div>
                )}
              </div>

              {/* 보조 KPI */}
              <div className="grid grid-cols-2 gap-3 md:col-span-7 md:grid-cols-3">
                <HeroStat
                  label="투자원금"
                  value={data.total_cost != null ? fmtWon(data.total_cost) : '—'}
                />
                <HeroStat
                  label="누적 수익률"
                  value={
                    typeof data.total_pnl_pct === 'number'
                      ? `${totalPctPos ? '+' : ''}${data.total_pnl_pct.toFixed(2)}%`
                      : '—'
                  }
                  valueClass={totalPctPos ? 'text-up' : 'text-down'}
                />
                <HeroStat label="보유종목" value={`${holdings.length}`} unit="종목" />
              </div>
            </div>

            {/* ───── vs BM 위험지표 스트립 (6칸) ───── */}
            <RiskStrip risk={risk} period={period} />

            {/* 미매칭 경고 */}
            {unmatched.length > 0 && (
              <div className="mt-5 flex items-start gap-2.5 rounded-chip border border-up/25 bg-up/[0.07] px-3.5 py-2.5">
                <AlertTriangle size={15} className="mt-0.5 shrink-0 text-up" />
                <p className="text-xs text-greige">
                  <span className="font-semibold text-up">가격 미매칭 {unmatched.length}건</span>
                  {' — '}
                  {unmatched.join(', ')}
                  <span className="text-muted"> · 자산마스터 이름 확인 필요</span>
                </p>
              </div>
            )}
          </div>
        </div>
      </motion.div>

      {/* ============ 손익 시계열 곡선 (vs BM) ============ */}
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-3 xl:items-stretch">
      <motion.div variants={item} className="xl:col-span-2 [&>*]:h-full">
        <PnlCurveCard
          state={curveState}
          curve={curve}
          chartData={chartData}
          mode={curveMode}
          onModeChange={setCurveMode}
          curveDisplay={curveDisplay}
          onCurveDisplayChange={setCurveDisplay}
          period={period}
          onPeriodChange={setPeriod}
          onRetry={() => loadCurve(period)}
          realizedPnlTotal={realizedPnlTotal}
        />
      </motion.div>

      <motion.div variants={item} className="xl:col-span-1 [&>*]:h-full">
        <ContributionCard holdings={holdings} />
      </motion.div>

      <motion.div variants={item} className="xl:col-span-2">
        <Card
          title="보유종목"
          eyebrow="Portfolio"
          action={
            <div className="flex flex-wrap items-center gap-2">
              <SegToggle
                options={[
                  { id: 'daily', label: '당일기준' },
                  { id: 'ytd', label: 'YTD' },
                  { id: 'cumulative', label: '누적기준' },
                ]}
                value={pnlBasis}
                onChange={v => setPnlBasis(v as PnlBasis)}
              />
              <Badge tone="neutral">{holdings.length} 종목</Badge>
            </div>
          }
          noPadding
        >
          {holdings.length === 0 ? (
            <div className="p-5">
              <EmptyState
                title="보유종목 없음"
                description="현재 평가 가능한 보유종목이 없습니다."
              />
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-line text-left font-mono text-[11px] uppercase tracking-[0.04em] text-muted">
                    <th className="px-5 py-2.5 font-semibold">종목</th>
                    <th className="px-3 py-2.5 text-right font-semibold">수량</th>
                    <th className="px-3 py-2.5 text-right font-semibold">취득단가</th>
                    <th className="px-3 py-2.5 text-right font-semibold">현재가</th>
                    <SortableTh
                      label="평가액"
                      sortKey="value"
                      activeSort={holdingSort}
                      onSort={handleHoldingSort}
                    />
                    <th className="px-3 py-2.5 text-right font-semibold">비중</th>
                    <SortableTh
                      label="손익"
                      sortKey="pnl"
                      activeSort={holdingSort}
                      onSort={handleHoldingSort}
                    />
                    <th className="px-3 py-2.5 text-right font-semibold">수익률</th>
                    {/* 작업2: 일간손익 컬럼 */}
                    <th className="hidden px-3 py-2.5 text-right font-semibold xl:table-cell">당일</th>
                    {/* 작업4: vs BM 컬럼 */}
                    <th className="hidden px-3 py-2.5 text-right font-semibold xl:table-cell">vs BM</th>
                    <th className="w-8 px-2 py-2.5" />
                  </tr>
                </thead>
                <tbody>
                  {displayedHoldings.map((h, i) => {
                    const display = getHoldingDisplayMetrics(h, pnlBasis)
                    const displayPrice =
                      h.usd_converted
                        ? (typeof h.live_price === 'number' && h.live_price > 0 ? h.live_price : h.price_native)
                        : (typeof h.live_price === 'number' && h.live_price > 0 ? h.live_price : h.price)
                    const pnlPos = display.pnl >= 0
                    const weightPct = ((display.value || 0) / totalValForWeight) * 100
                    const barPct = Math.min(100, (Math.abs(display.pnl_pct || 0) / maxAbsPct) * 100)
                    const hasBmCol =
                      typeof h.excess_vs_bm_pct === 'number'
                    const hasDailyPnl =
                      typeof h.daily_pnl_pct === 'number'
                    return (
                      <tr
                        key={`${h.name}-${i}`}
                        onClick={() => setSelected(h)}
                        className="group cursor-pointer border-b border-line/50 transition-colors last:border-0 hover:bg-card-2/50"
                      >
                        <td className="px-5 py-3">
                          <div className="flex items-center gap-2">
                            <span className="truncate font-sans font-medium text-beige">
                              {h.name}
                            </span>
                            {!h.matched && (
                              <span
                                className="h-1.5 w-1.5 shrink-0 rounded-full bg-up"
                                title="가격 미매칭"
                              />
                            )}
                          </div>
                          {h.live_code && (
                            <span className="font-mono text-[10px] text-muted">
                              {h.live_code}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-3 text-right font-mono tabular-nums text-greige">
                          {h.qty.toLocaleString('ko-KR')}
                        </td>
                        <td className="px-3 py-3 text-right font-mono tabular-nums text-greige">
                          {h.usd_converted ? fmtUsd(h.unit_cost) : Math.round(h.unit_cost).toLocaleString('ko-KR')}
                        </td>
                        <td className="px-3 py-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <span className="font-mono tabular-nums text-beige">
                              {h.usd_converted
                                ? fmtUsd(displayPrice)
                                : Math.round(displayPrice ?? 0).toLocaleString('ko-KR')}
                            </span>
                            <Badge
                              tone={h.usd_converted ? 'neutral' : h.price_kind === '기준가' ? 'purple' : 'blue'}
                              className="px-1.5 py-0 text-[9px] normal-case tracking-normal"
                            >
                              {h.usd_converted ? 'USD' : h.price_kind === '기준가' ? '기준가' : '현재가'}
                            </Badge>
                            {h.live_source && (
                              <Badge
                                tone="neutral"
                                className="px-1.5 py-0 text-[9px] normal-case tracking-normal"
                              >
                                {h.live_source}
                              </Badge>
                            )}
                          </div>
                        </td>
                        <td className="px-3 py-3 text-right font-mono tabular-nums text-beige">
                          {fmtWon(display.value)}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <span className="font-mono text-xs tabular-nums text-greige">
                              {weightPct.toFixed(1)}%
                            </span>
                            <span className="hidden h-1.5 w-12 overflow-hidden rounded-pill bg-card-2 sm:block">
                              <span
                                className="block h-full rounded-pill bg-hanwha/70"
                                style={{ width: `${Math.min(100, weightPct)}%` }}
                              />
                            </span>
                          </div>
                        </td>
                        <td
                          className={cn(
                            'px-3 py-3 text-right font-mono tabular-nums font-semibold',
                            pnlPos ? 'text-up' : 'text-down',
                          )}
                        >
                          {fmtWon(display.pnl, true)}
                        </td>
                        <td className="px-3 py-3">
                          <div className="flex items-center justify-end gap-2">
                            <span className="hidden h-1.5 w-12 overflow-hidden rounded-pill bg-card-2 sm:block">
                              <span
                                className={cn('block h-full rounded-pill', pnlPos ? 'bg-up/70' : 'bg-down/70')}
                                style={{ width: `${barPct}%` }}
                              />
                            </span>
                            <ChangePill value={display.pnl_pct} size="sm" />
                          </div>
                        </td>
                        {/* 작업2: 당일 손익 컬럼 */}
                        <td className="hidden px-3 py-3 text-right xl:table-cell">
                          {hasDailyPnl ? (
                            <ChangePill value={h.daily_pnl_pct!} size="sm" />
                          ) : (
                            <span className="font-mono text-[11px] text-muted">—</span>
                          )}
                        </td>
                        {/* 작업4: vs BM 컬럼 */}
                        <td className="hidden px-3 py-3 text-right xl:table-cell">
                          {hasBmCol ? (
                            <div className="flex flex-col items-end gap-0.5">
                              <ChangePill value={h.excess_vs_bm_pct!} size="sm" />
                              {h.bm && (
                                <span className="font-mono text-[9px] text-muted">
                                  {h.bm}
                                </span>
                              )}
                            </div>
                          ) : (
                            <span className="font-mono text-[11px] text-muted">—</span>
                          )}
                        </td>
                        <td className="px-2 py-3 text-center">
                          <ChevronRight
                            size={15}
                            className="text-muted opacity-0 transition-opacity group-hover:opacity-100"
                          />
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
                <tfoot>
                  <tr className="border-t border-hanwha/40 bg-card-2/60 font-mono text-[12px] font-bold text-beige">
                    <td className="px-5 py-3">소계</td>
                    <td className="px-3 py-3 text-right text-muted" colSpan={3}>
                      {displayedHoldings.length} 종목
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums">
                      {fmtWon(holdingsSubtotal.value)}
                    </td>
                    <td className="px-3 py-3 text-right tabular-nums text-greige">100.0%</td>
                    <td
                      className={cn(
                        'px-3 py-3 text-right tabular-nums',
                        subtotalPos ? 'text-up' : 'text-down',
                      )}
                    >
                      {fmtWon(holdingsSubtotal.pnl, true)}
                    </td>
                    <td className="px-3 py-3 text-right">
                      <ChangePill value={holdingsSubtotal.pnl_pct} size="sm" />
                    </td>
                    <td className="px-3 py-3 text-muted" colSpan={3}>
                      {pnlBasis === 'daily' ? '당일기준' : pnlBasis === 'ytd' ? 'YTD' : '누적기준'}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          )}
        </Card>
      </motion.div>

      <motion.div variants={item} className="space-y-6 xl:col-span-1">
        <RollingRiskPanel rollingRisk={rollingRisk} />
        <AttributionCard attribution={attribution} />
      </motion.div>

      <motion.div variants={item} className="xl:col-span-2">
        <SectionHeader
          eyebrow="Newsflow"
          title="보유종목 뉴스 / 공시"
          description="포트폴리오 편입 종목의 실시간 뉴스·공시 흐름"
          action={
            <a
              href="https://finance.naver.com"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-hanwha transition-opacity hover:opacity-80"
            >
              네이버 금융 <ArrowUpRight size={13} />
            </a>
          }
        />
        <NewsFlow
          apiBase={apiBase}
          holdings={holdings.map(h => ({ name: h.name, code: h.live_code ?? '' }))}
        />
      </motion.div>

      <motion.div variants={item} className="xl:col-span-1">
        <TradesCard
          tradesData={tradesData}
          tradesLoading={tradesLoading}
          tradesOffset={tradesOffset}
          tradesLimit={TRADES_LIMIT}
          onLoadMore={() => loadTrades(tradesOffset + TRADES_LIMIT, true)}
        />
      </motion.div>
      </div>

      {/* ============ 상세 드로어 ============ */}
      <HoldingDrawer
        holding={selected}
        apiBase={apiBase}
        onClose={() => setSelected(null)}
        onConvene={goToCommittee}
      />
    </motion.div>
  )
}

function SortableTh({
  label,
  sortKey,
  activeSort,
  onSort,
}: {
  label: string
  sortKey: HoldingSortKey
  activeSort: SortState
  onSort: (key: HoldingSortKey) => void
}) {
  const active = activeSort?.key === sortKey
  const mark = !active ? '↕' : activeSort.dir === 'desc' ? '↓' : '↑'
  return (
    <th className="px-3 py-2.5 text-right font-semibold">
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        className={cn(
          'inline-flex items-center justify-end gap-1 rounded-pill px-1.5 py-0.5 transition-colors hover:bg-card-2 hover:text-beige',
          active ? 'text-hanwha' : 'text-muted',
        )}
      >
        <span>{label}</span>
        <span className="text-[10px]">{mark}</span>
      </button>
    </th>
  )
}

function HeroStat({
  label,
  value,
  unit,
  valueClass,
}: {
  label: string
  value: string
  unit?: string
  valueClass?: string
}) {
  return (
    <div className="flex flex-col justify-center gap-1 rounded-chip border border-line bg-card-2/40 px-3.5 py-3">
      <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
        {label}
      </span>
      <span className={cn('font-mono text-lg font-bold tabular-nums leading-none text-beige', valueClass)}>
        {value}
        {unit && <span className="ml-1 text-xs font-medium text-muted">{unit}</span>}
      </span>
    </div>
  )
}

// ── vs BM 위험지표 스트립 (8칸: 기존 6 + Sharpe + Calmar) ───────────────
function RiskStrip({ risk, period }: { risk: RiskData | null; period: Period }) {
  if (!risk) {
    return (
      <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-[58px] rounded-chip" />
        ))}
      </div>
    )
  }

  // 한국관례 등락색: 초과수익·정보비율·Sharpe·Calmar는 +면 레드/–면 블루.
  // MDD는 손실이므로 항상 down. TE·베타·연율변동성은 리스크 크기라 중립(beige).
  const cells: Array<{ label: string; value: string; valueClass?: string; hint: string }> = [
    {
      label: '초과수익',
      value: fmtPct(risk.excess_return, 2, true),
      valueClass: risk.excess_return >= 0 ? 'text-up' : 'text-down',
      hint: `포트 연율수익 − BM 연율수익 (BM ${fmtPct(risk.bm_ann_return)})`,
    },
    { label: '추적오차 TE', value: fmtPct(risk.tracking_error), hint: '초과수익 일별표준편차 × √252' },
    {
      label: 'MDD',
      value: fmtPct(risk.mdd),
      valueClass: 'text-down',
      hint: '최대낙폭 = min(평가액/직전고점 − 1)',
    },
    { label: '베타 β', value: risk.beta.toFixed(2), hint: 'cov(r_p, r_b) / var(r_b), 전 구간 회귀' },
    {
      label: '정보비율 IR',
      value: risk.info_ratio.toFixed(2),
      valueClass: risk.info_ratio >= 0 ? 'text-up' : 'text-down',
      hint: '초과수익 / 추적오차',
    },
    { label: '연율변동성', value: fmtPct(risk.ann_vol), hint: '일별수익 표준편차 × √252' },
    {
      label: 'Sharpe',
      value: risk.sharpe != null ? risk.sharpe.toFixed(2) : '—',
      valueClass: risk.sharpe != null ? (risk.sharpe >= 0 ? 'text-up' : 'text-down') : undefined,
      hint: '연율수익 / 연율변동성 (무위험이자율=0)',
    },
    {
      label: 'Calmar',
      value: risk.calmar != null ? risk.calmar.toFixed(2) : '—',
      valueClass: risk.calmar != null ? (risk.calmar >= 0 ? 'text-up' : 'text-down') : undefined,
      hint: '연율수익 / |MDD| (MDD≈0이면 —)',
    },
  ]

  const coverageWarn = risk.coverage_pct < 100

  return (
    <div className="mt-5">
      <div className="mb-2 flex flex-wrap items-center gap-2">
        <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
          vs BM 위험지표
        </span>
        <Badge tone="blue" className="px-1.5 py-0 text-[9px] normal-case tracking-normal">
          {risk.bm_name || 'BM'}
        </Badge>
        <span className="font-mono text-[10px] text-muted">· {period === 'MAX' ? '전체' : period}</span>
        {coverageWarn && (
          <Badge tone="up" className="px-1.5 py-0 text-[9px] normal-case tracking-normal">
            BM 일부 미매핑 {risk.coverage_pct.toFixed(0)}%
          </Badge>
        )}
        {risk.default_bm_used && (
          <Badge tone="neutral" className="px-1.5 py-0 text-[9px] normal-case tracking-normal">
            디폴트 BM 포함
          </Badge>
        )}
        {/* methodology: 작은 글씨 + 호버 툴팁 */}
        <span
          className="group/methodology relative ml-auto inline-flex cursor-help items-center gap-1 font-mono text-[10px] text-muted"
          title={risk.methodology}
        >
          <Info size={11} />
          산식 · n={risk.n_obs}
          <span className="pointer-events-none absolute right-0 top-full z-20 mt-1 hidden w-72 rounded-chip border border-line bg-card px-3 py-2 text-left text-[10px] leading-relaxed text-greige shadow-card group-hover/methodology:block">
            {risk.methodology}
          </span>
        </span>
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-8">
        {cells.map(c => (
          <div
            key={c.label}
            title={c.hint}
            className="flex flex-col justify-center gap-1 rounded-chip border border-line bg-card-2/40 px-3 py-2.5"
          >
            <span className="truncate font-mono text-[10px] font-semibold uppercase tracking-[0.04em] text-muted">
              {c.label}
            </span>
            <span className={cn('font-mono text-base font-bold tabular-nums leading-none text-beige', c.valueClass)}>
              {c.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── 작업1: 종목별 기여도 카드 ────────────────────────────────────────────
type ContributionHolding = {
  name: string
  contribution_pct?: number | null
}

function ContributionCard({ holdings }: { holdings: ContributionHolding[] }) {
  // contribution_pct 가 있는 종목만 필터, 내림차순 정렬
  const items = holdings
    .filter(h => typeof h.contribution_pct === 'number')
    .sort((a, b) => (b.contribution_pct ?? 0) - (a.contribution_pct ?? 0))

  if (items.length === 0) return null

  // 절대값 최대치 (막대 정규화)
  const maxAbs = items.reduce((m, h) => Math.max(m, Math.abs(h.contribution_pct ?? 0)), 0.001)

  // 상위 기여/손실 각 3개 하이라이트
  const topGainers = items.slice(0, 3)
  const topLosers = [...items].reverse().slice(0, 3).filter(h => (h.contribution_pct ?? 0) < 0)

  return (
    <Card
      className="h-full"
      eyebrow="Contribution"
      title="손익 기여도"
      action={
        <span className="font-mono text-[10px] text-muted">무엇이 총손익을 끌었나</span>
      }
    >
      {/* 상위 기여 / 하락 요약 칩 */}
      {(topGainers.length > 0 || topLosers.length > 0) && (
        <div className="mb-4 flex flex-wrap gap-2">
          {topGainers.map(h => (
            <span
              key={`gain-${h.name}`}
              className="inline-flex items-center gap-1.5 rounded-pill bg-up/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-up"
            >
              <span className="text-[0.85em]">▲</span>
              {h.name}
              <span className="font-normal text-up/70">
                +{(h.contribution_pct ?? 0).toFixed(2)}%
              </span>
            </span>
          ))}
          {topLosers.map(h => (
            <span
              key={`loss-${h.name}`}
              className="inline-flex items-center gap-1.5 rounded-pill bg-down/10 px-2.5 py-1 font-mono text-[11px] font-semibold text-down"
            >
              <span className="text-[0.85em]">▼</span>
              {h.name}
              <span className="font-normal text-down/70">
                {(h.contribution_pct ?? 0).toFixed(2)}%
              </span>
            </span>
          ))}
        </div>
      )}

      {/* Diverging bar chart */}
      <ResponsiveContainer width="100%" height={Math.max(180, items.length * 32)}>
        <BarChart
          data={items.map(h => ({ name: h.name, value: h.contribution_pct ?? 0 }))}
          layout="vertical"
          margin={{ top: 0, right: 48, left: 4, bottom: 0 }}
        >
          <CartesianGrid stroke={C.line} strokeOpacity={0.3} horizontal={false} />
          <XAxis
            type="number"
            domain={[-maxAbs * 1.1, maxAbs * 1.1]}
            tick={{ fill: C.muted, fontSize: 10, fontFamily: 'IBM Plex Mono, monospace' }}
            tickLine={false}
            axisLine={{ stroke: C.line }}
            tickFormatter={(v: number) => `${v > 0 ? '+' : ''}${v.toFixed(1)}%`}
          />
          <YAxis
            type="category"
            dataKey="name"
            width={90}
            tick={{ fill: C.greige, fontSize: 11, fontFamily: 'Noto Sans KR, sans-serif' }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: 'rgba(255,255,255,0.03)' }}
            contentStyle={{
              background: C.card,
              border: `1px solid ${C.line}`,
              borderRadius: 11,
              fontSize: 12,
              fontFamily: 'IBM Plex Mono, Pretendard, Noto Sans KR, monospace',
              color: C.beige,
            }}
            labelStyle={{ color: C.greige, marginBottom: 4 }}
            formatter={(value: unknown) => {
              const v = value as number
              return [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, '기여도']
            }}
          />
          <Bar dataKey="value" radius={[0, 3, 3, 0]} maxBarSize={20}>
            {items.map((h, idx) => (
              <Cell
                key={`cell-${idx}`}
                fill={(h.contribution_pct ?? 0) >= 0 ? C.up : C.down}
                fillOpacity={0.8}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </Card>
  )
}

// ── 손익 시계열 곡선 (포트 vs BM 오버레이) ───────────────────────────────
type ChartPoint = {
  date: string
  port: number | null
  bm: number | null
  cum: number | null
  realizedCum: number | null
  totalInclRealized: number | null
}

function PnlCurveCard({
  state,
  curve,
  chartData,
  mode,
  onModeChange,
  curveDisplay,
  onCurveDisplayChange,
  period,
  onPeriodChange,
  onRetry,
  realizedPnlTotal,
}: {
  state: 'loading' | 'done' | 'error'
  curve: CurveData | null
  chartData: ChartPoint[]
  mode: CurveMode
  onModeChange: (m: CurveMode) => void
  curveDisplay: CurveDisplay
  onCurveDisplayChange: (d: CurveDisplay) => void
  period: Period
  onPeriodChange: (p: Period) => void
  onRetry: () => void
  realizedPnlTotal: number | null
}) {
  // 작업3: 어떤 시리즈를 보여줄지
  const activeKey: keyof ChartPoint =
    mode === 'cumulative'
      ? 'port'
      : curveDisplay === 'total'
        ? 'totalInclRealized'
        : curveDisplay === 'realized'
          ? 'realizedCum'
          : 'cum'

  const hasData = chartData.some(d => d[activeKey] != null)

  // 작업3: 실현+평가/실현 시리즈 존재 여부
  const hasRealizedData = chartData.some(d => d.realizedCum != null || d.totalInclRealized != null)

  return (
    <Card
      className="h-full"
      eyebrow="P&L Curve"
      title="손익 시계열"
      action={
        <div className="flex flex-wrap items-center gap-2">
          {/* 누적/일간 토글 */}
          <SegToggle
            options={[
              { id: 'cumulative', label: '누적' },
              { id: 'daily', label: '누적손익' },
            ]}
            value={mode}
            onChange={v => onModeChange(v as CurveMode)}
          />
          {/* 작업3: 곡선 표시 토글 (누적손익 모드일 때만) */}
          {mode === 'daily' && hasRealizedData && (
            <SegToggle
              options={[
                { id: 'eval', label: '평가손익' },
                { id: 'total', label: '실현+평가' },
                { id: 'realized', label: '실현누적' },
              ]}
              value={curveDisplay}
              onChange={v => onCurveDisplayChange(v as CurveDisplay)}
            />
          )}
          {/* 기간 토글 */}
          <SegToggle
            options={PERIODS.map(p => ({ id: p.id, label: p.label }))}
            value={period}
            onChange={v => onPeriodChange(v as Period)}
          />
        </div>
      }
    >
      {/* 작업3: 실현손익 누계 헤더 칩 */}
      {realizedPnlTotal != null && (
        <div className="mb-3 flex items-center gap-2">
          <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
            실현손익 누계
          </span>
          <span
            className={cn(
              'font-mono text-sm font-bold tabular-nums',
              realizedPnlTotal >= 0 ? 'text-up' : 'text-down',
            )}
          >
            {fmtWon(realizedPnlTotal, true)}
          </span>
        </div>
      )}

      {state === 'loading' ? (
        <Skeleton className="h-[280px] w-full rounded-card" />
      ) : state === 'error' ? (
        <ErrorState
          title="손익 곡선을 불러오지 못했습니다"
          message="시계열 데이터를 가져오지 못했습니다. 다시 시도하세요."
          onRetry={onRetry}
        />
      ) : !hasData ? (
        <EmptyState
          icon={<LineChartIcon size={20} strokeWidth={1.75} />}
          title="시계열 데이터 없음"
          description="이 기간에는 표시할 손익 곡선이 없습니다."
        />
      ) : (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 font-mono text-[11px] text-muted">
            {mode === 'cumulative' ? (
              <>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full bg-up" />
                  포트폴리오
                </span>
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-0.5 w-4 rounded-full bg-down" />
                  {curve?.bm_name || 'BM'} {curve?.bm_resolved ? '' : '(미해결)'}
                </span>
              </>
            ) : (
              <span className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full bg-hanwha" />
                {curveDisplay === 'eval' ? '평가손익' : curveDisplay === 'total' ? '실현+평가 합산' : '실현손익 누적'}
              </span>
            )}
            <span className="ml-auto">
              {curve?.days ?? 0}일 ·{' '}
              {mode === 'cumulative' ? '시작 100 리베이스' : '누적손익(억원)'}
            </span>
          </div>
          <ResponsiveContainer width="100%" height={280}>
            <AreaChart data={chartData} margin={{ top: 6, right: 12, left: 4, bottom: 0 }}>
              <defs>
                <linearGradient id="pnlPortFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.up} stopOpacity={0.28} />
                  <stop offset="100%" stopColor={C.up} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="pnlCumFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.hanwha} stopOpacity={0.22} />
                  <stop offset="100%" stopColor={C.hanwha} stopOpacity={0} />
                </linearGradient>
                <linearGradient id="pnlRealizedFill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={C.blue} stopOpacity={0.22} />
                  <stop offset="100%" stopColor={C.blue} stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke={C.line} strokeOpacity={0.4} vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={{ stroke: C.line }}
                minTickGap={56}
              />
              <YAxis
                width={52}
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={false}
                domain={['auto', 'auto']}
                tickFormatter={(v: number) =>
                  mode === 'cumulative'
                    ? v.toFixed(0)
                    : fmtWon(v)
                }
              />
              <Tooltip
                labelStyle={{ color: C.greige, fontFamily: 'Pretendard, Noto Sans KR', fontSize: 11 }}
                contentStyle={{
                  background: C.card,
                  border: `1px solid ${C.line}`,
                  borderRadius: 11,
                  fontSize: 12,
                  fontFamily: 'Pretendard, Noto Sans KR',
                  color: C.beige,
                }}
                cursor={{ stroke: C.line, strokeWidth: 1 }}
                formatter={(value: unknown, name: unknown) => {
                  const v = value as number | null
                  if (v == null) return ['—', String(name)]
                  if (name === 'cum') return [fmtWon(v, true), '평가손익']
                  if (name === 'totalInclRealized') return [fmtWon(v, true), '실현+평가']
                  if (name === 'realizedCum') return [fmtWon(v, true), '실현손익 누적']
                  const label = name === 'bm' ? (curve?.bm_name || 'BM') : '포트폴리오'
                  return [v.toFixed(2), label]
                }}
              />
              {mode === 'cumulative' ? (
                <>
                  <Area
                    type="monotone"
                    dataKey="port"
                    name="port"
                    stroke={C.up}
                    strokeWidth={2.2}
                    fill="url(#pnlPortFill)"
                    dot={false}
                    activeDot={{ r: 3.5, fill: C.up }}
                    connectNulls
                  />
                  <Line
                    type="monotone"
                    dataKey="bm"
                    name="bm"
                    stroke={C.down}
                    strokeWidth={1.6}
                    strokeDasharray="4 3"
                    dot={false}
                    activeDot={{ r: 3, fill: C.down }}
                    connectNulls
                  />
                </>
              ) : curveDisplay === 'total' ? (
                <Area
                  type="monotone"
                  dataKey="totalInclRealized"
                  name="totalInclRealized"
                  stroke={C.hanwha}
                  strokeWidth={2.2}
                  fill="url(#pnlCumFill)"
                  dot={false}
                  activeDot={{ r: 3.5, fill: C.hanwha }}
                  connectNulls
                />
              ) : curveDisplay === 'realized' ? (
                <Area
                  type="monotone"
                  dataKey="realizedCum"
                  name="realizedCum"
                  stroke={C.blue}
                  strokeWidth={2.2}
                  fill="url(#pnlRealizedFill)"
                  dot={false}
                  activeDot={{ r: 3.5, fill: C.blue }}
                  connectNulls
                />
              ) : (
                <Area
                  type="monotone"
                  dataKey="cum"
                  name="cum"
                  stroke={C.hanwha}
                  strokeWidth={2.2}
                  fill="url(#pnlCumFill)"
                  dot={false}
                  activeDot={{ r: 3.5, fill: C.hanwha }}
                  connectNulls
                />
              )}
            </AreaChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}

// ── 작은 세그먼트 토글 (토큰 기반) ──────────────────────────────────────
function SegToggle({
  options,
  value,
  onChange,
}: {
  options: ReadonlyArray<{ id: string; label: string }>
  value: string
  onChange: (id: string) => void
}) {
  return (
    <div className="inline-flex items-center gap-0.5 rounded-pill border border-line bg-card-2/40 p-0.5">
      {options.map(o => {
        const active = o.id === value
        return (
          <button
            key={o.id}
            onClick={() => onChange(o.id)}
            className={cn(
              'rounded-pill px-2.5 py-1 font-mono text-[11px] font-semibold tabular-nums transition-colors',
              active ? 'bg-hanwha text-canvas' : 'text-muted hover:text-beige',
            )}
          >
            {o.label}
          </button>
        )
      })}
    </div>
  )
}

// ── 자산군 기여 분석 카드 ─────────────────────────────────────────────────
function AttributionCard({ attribution }: { attribution: AttributionData | null }) {
  if (!attribution) return null
  const { groups, total_market_value, total_pnl } = attribution
  if (!groups || groups.length === 0) return null

  const maxAbs = groups.reduce((m, g) => Math.max(m, Math.abs(g.pnl_contribution_pct)), 0.001)
  const totalPos = total_pnl >= 0

  return (
    <Card
      eyebrow="Attribution"
      title="자산군 기여 분석"
      action={
        <span className="font-mono text-[10px] text-muted">
          BM 기준 그룹 · 총평가 {(total_market_value / 1e8).toFixed(1)}억
        </span>
      }
    >
      {/* 헤더 행 */}
      <div className="mb-2 grid grid-cols-[1fr_56px_56px_80px_52px_56px] gap-x-2 px-1 font-mono text-[10px] font-semibold uppercase tracking-[0.04em] text-muted">
        <span>자산군</span>
        <span className="text-right">비중</span>
        <span className="text-right">평가(억)</span>
        <span className="text-right">기여도</span>
        <span className="text-right">평균수익</span>
        <span className="text-right">종목수</span>
      </div>

      <div className="space-y-1.5">
        {groups.map(g => {
          const contribPos = g.pnl_contribution_pct >= 0
          const retPos = g.avg_return_pct >= 0
          const barPct = Math.min(100, (Math.abs(g.pnl_contribution_pct) / maxAbs) * 100)
          return (
            <div
              key={g.group}
              className="grid grid-cols-[1fr_56px_56px_80px_52px_56px] items-center gap-x-2 rounded-chip border border-line/40 bg-card-2/30 px-3 py-2"
            >
              {/* 자산군명 */}
              <span className="truncate font-sans text-[12px] font-medium text-beige" title={g.group}>
                {g.group}
              </span>
              {/* 비중% */}
              <span className="text-right font-mono text-[11px] tabular-nums text-greige">
                {g.weight_pct.toFixed(1)}%
              </span>
              {/* 평가액 (억원) */}
              <span className="text-right font-mono text-[11px] tabular-nums text-greige">
                {(g.market_value / 1e8).toFixed(1)}
              </span>
              {/* 기여도 (발산 막대 + 수치) */}
              <div className="flex items-center justify-end gap-1.5">
                <div className="relative h-1.5 w-20 overflow-hidden rounded-pill bg-card-2">
                  {/* 중앙 기준선 */}
                  <span className="absolute inset-y-0 left-1/2 w-px bg-line/60" />
                  <span
                    className={cn('absolute inset-y-0 rounded-pill', contribPos ? 'bg-up/70' : 'bg-down/70')}
                    style={
                      contribPos
                        ? { left: '50%', width: `${barPct / 2}%` }
                        : { right: '50%', width: `${barPct / 2}%` }
                    }
                  />
                </div>
                <span
                  className={cn(
                    'font-mono text-[11px] font-semibold tabular-nums',
                    contribPos ? 'text-up' : 'text-down',
                  )}
                >
                  {g.pnl_contribution_pct > 0 ? '+' : ''}{g.pnl_contribution_pct.toFixed(1)}%
                </span>
              </div>
              {/* 평균수익률 */}
              <span
                className={cn(
                  'text-right font-mono text-[11px] tabular-nums',
                  retPos ? 'text-up' : 'text-down',
                )}
              >
                {g.avg_return_pct > 0 ? '+' : ''}{g.avg_return_pct.toFixed(1)}%
              </span>
              {/* 종목수 */}
              <span className="text-right font-mono text-[11px] tabular-nums text-muted">
                {g.holdings_count}
              </span>
            </div>
          )
        })}
      </div>

      {/* 합계 행 */}
      <div className="mt-2 flex items-center justify-between rounded-chip border border-hanwha/30 bg-card-2/50 px-3 py-2 font-mono text-[11px]">
        <span className="font-semibold text-greige">합계 손익</span>
        <span className={cn('font-bold tabular-nums', totalPos ? 'text-up' : 'text-down')}>
          {totalPos ? '+' : ''}{(total_pnl / 1e8).toFixed(2)}억
        </span>
      </div>
    </Card>
  )
}

// ── Task C: 매도내역 paginated + enriched table ───────────────────────────
function TradesCard({
  tradesData,
  tradesLoading,
  tradesOffset,
  tradesLimit,
  onLoadMore,
}: {
  tradesData: TradesData | null
  tradesLoading: boolean
  tradesOffset: number
  tradesLimit: number
  onLoadMore: () => void
}) {
  const trades = tradesData?.trades ?? []
  const total = tradesData?.total ?? 0
  const hasMore = tradesOffset + tradesLimit < total

  return (
    <details className="group rounded-card border border-line bg-card shadow-card">
      <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-5 py-4">
        <span>
          <span className="block font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
            Realized
          </span>
          <span className="font-display text-base font-bold text-beige">매도내역</span>
        </span>
        <div className="flex items-center gap-2">
          {tradesData?.sells_col_fallback && (
            <Badge tone="up" className="px-1.5 py-0 text-[9px] normal-case tracking-normal">
              컬럼 위치 추정
            </Badge>
          )}
          <Badge tone="neutral" className="group-open:hidden">
            접힘 · {total}건
          </Badge>
          <Badge tone="blue" className="hidden group-open:inline-flex">펼침</Badge>
        </div>
      </summary>
      <div className="border-t border-line">
        {trades.length === 0 && !tradesLoading ? (
          <div className="p-5">
            <EmptyState
              icon={<Receipt size={20} strokeWidth={1.75} />}
              title="매도내역 없음"
              description="실현된 매도 거래가 아직 없습니다."
            />
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-y border-line text-left font-mono text-[11px] uppercase tracking-[0.04em] text-muted">
                    <th className="px-5 py-2.5 font-semibold">종목</th>
                    <th className="px-3 py-2.5 font-semibold">매도일</th>
                    <th className="px-3 py-2.5 text-right font-semibold">수량</th>
                    <th className="px-3 py-2.5 text-right font-semibold">매입단가</th>
                    <th className="px-3 py-2.5 text-right font-semibold">매도단가</th>
                    <th className="px-3 py-2.5 text-right font-semibold">보유일</th>
                    <th className="px-3 py-2.5 text-right font-semibold">실현손익</th>
                    <th className="px-3 py-2.5 text-right font-semibold">수익률</th>
                    <th className="px-5 py-2.5 text-right font-semibold">누적손익</th>
                  </tr>
                </thead>
                <tbody>
                  {trades.map((t, i) => {
                    const pnlPos = t.pnl == null ? null : t.pnl >= 0
                    const cumPos = t.cum_pnl >= 0
                    return (
                      <tr
                        key={`${t.name}-${t.sell_date}-${i}`}
                        className="border-b border-line/50 transition-colors last:border-0 hover:bg-card-2/50"
                      >
                        <td className="px-5 py-2.5 font-sans text-beige">{t.name}</td>
                        <td className="px-3 py-2.5 font-mono tabular-nums text-greige">
                          {t.sell_date || '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-greige">
                          {t.qty || '—'}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-greige">
                          {t.avg_buy_price == null
                            ? '—'
                            : Math.round(t.avg_buy_price).toLocaleString('ko-KR')}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-greige">
                          {t.avg_sell_price == null
                            ? '—'
                            : Math.round(t.avg_sell_price).toLocaleString('ko-KR')}
                        </td>
                        <td className="px-3 py-2.5 text-right font-mono tabular-nums text-greige">
                          {t.holding_days == null ? '—' : `${t.holding_days}일`}
                        </td>
                        <td
                          className={cn(
                            'px-3 py-2.5 text-right font-mono tabular-nums font-semibold',
                            pnlPos == null ? 'text-muted' : pnlPos ? 'text-up' : 'text-down',
                          )}
                        >
                          {t.pnl == null ? '—' : fmtWon(t.pnl, true)}
                        </td>
                        <td className="px-3 py-2.5 text-right">
                          {t.return_pct == null ? (
                            <span className="font-mono text-muted">—</span>
                          ) : (
                            <span className="inline-flex justify-end">
                              <ChangePill value={t.return_pct} size="sm" />
                            </span>
                          )}
                        </td>
                        <td
                          className={cn(
                            'px-5 py-2.5 text-right font-mono tabular-nums text-xs',
                            cumPos ? 'text-up' : 'text-down',
                          )}
                        >
                          {fmtWon(t.cum_pnl, true)}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
            {/* 더 보기 / 페이지네이션 */}
            {(hasMore || tradesLoading) && (
              <div className="flex items-center justify-between border-t border-line/50 px-5 py-3">
                <span className="font-mono text-[11px] text-muted">
                  {trades.length} / {total}건 표시
                </span>
                <button
                  type="button"
                  disabled={tradesLoading}
                  onClick={onLoadMore}
                  className={cn(
                    'inline-flex items-center gap-1.5 rounded-pill border border-line bg-card-2/40 px-3.5 py-1.5 font-mono text-[11px] font-semibold text-greige transition-colors hover:border-hanwha/60 hover:text-beige',
                    tradesLoading && 'cursor-not-allowed opacity-50',
                  )}
                >
                  {tradesLoading ? '로딩 중…' : '더 보기'}
                </button>
              </div>
            )}
            {!hasMore && trades.length > 0 && (
              <div className="border-t border-line/50 px-5 py-2.5 font-mono text-[11px] text-muted">
                전체 {total}건 표시 완료
              </div>
            )}
          </>
        )}
      </div>
    </details>
  )
}

// ── 롤링 위험지표 패널 (Sparkline × 2) ───────────────────────────────────
function RollingRiskPanel({ rollingRisk }: { rollingRisk: RollingRiskData | null }) {
  if (!rollingRisk || rollingRisk.dates.length === 0) return null

  // null 제거한 유효값 배열 (Sparkline은 number[] 요구)
  const betaVals = rollingRisk.beta.filter((v): v is number => v != null)
  const irVals   = rollingRisk.ir.filter((v): v is number => v != null)

  const lastBeta = betaVals.length > 0 ? betaVals[betaVals.length - 1] : null
  const lastIr   = irVals.length > 0   ? irVals[irVals.length - 1]     : null

  return (
    <Card
      eyebrow="Rolling Risk"
      title="롤링 위험지표"
      action={
        <span className="font-mono text-[10px] text-muted">
          {rollingRisk.window}일 롤링 · {rollingRisk.dates.length}pt
        </span>
      }
    >
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        {/* 롤링 베타 */}
        <div className="rounded-chip border border-line bg-card-2/30 px-4 py-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
              롤링 베타 β
            </span>
            {lastBeta != null && (
              <span className="font-mono text-base font-bold tabular-nums text-beige">
                {lastBeta.toFixed(2)}
              </span>
            )}
          </div>
          {betaVals.length >= 2 ? (
            <Sparkline
              data={betaVals}
              width={260}
              height={48}
              color="var(--blue)"
              area
              className="w-full"
            />
          ) : (
            <span className="font-mono text-[11px] text-muted">데이터 부족</span>
          )}
          <div className="mt-1 font-mono text-[10px] text-muted">
            cov(r_p, r_b) / var(r_b) — {rollingRisk.window}일 롤링
          </div>
        </div>

        {/* 롤링 IR */}
        <div className="rounded-chip border border-line bg-card-2/30 px-4 py-3">
          <div className="mb-1 flex items-center justify-between">
            <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
              롤링 정보비율 IR
            </span>
            {lastIr != null && (
              <span
                className={cn(
                  'font-mono text-base font-bold tabular-nums',
                  lastIr >= 0 ? 'text-up' : 'text-down',
                )}
              >
                {lastIr.toFixed(2)}
              </span>
            )}
          </div>
          {irVals.length >= 2 ? (
            <Sparkline
              data={irVals}
              width={260}
              height={48}
              area
              className="w-full"
            />
          ) : (
            <span className="font-mono text-[11px] text-muted">데이터 부족</span>
          )}
          <div className="mt-1 font-mono text-[10px] text-muted">
            mean(excess) / std(excess) × √252 — {rollingRisk.window}일 롤링
          </div>
        </div>
      </div>
    </Card>
  )
}
