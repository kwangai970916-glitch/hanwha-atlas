import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { Activity, TrendingUp } from 'lucide-react'
import { CandleChart } from './CandleChart'
import { DataTable } from './DataTable'
import {
  Card,
  ChangePill,
  EmptyState,
  ErrorState,
  MetricCard,
  SectionHeader,
  Skeleton,
} from './ui'
import { MarketRadar } from './market/MarketRadar'
import { Movers } from './market/Movers'
import { SectorTreemap } from './market/SectorTreemap'
import { CommitteeLatestWidget } from './market/CommitteeLatestWidget'
import { BriefingLatestWidget } from './market/BriefingLatestWidget'
import { MarketNewsFlow } from './market/MarketNewsFlow'
import { EconomicCalendar } from './market/EconomicCalendar'

type Tick = {
  symbol: string
  display: string
  price: number
  change: number
  asset_type: string
  sector?: string
}

/** /api/market/snapshot 응답 */
type SnapshotTick = { symbol: string; display?: string; source?: string | null; asset_type?: string }
type SnapshotResponse = { ticks?: SnapshotTick[]; price_as_of?: string; fetched_at?: string }

/** /api/market/kpi 응답 */
type KpiQuote = { value: number | null; change: number | null; change_pct?: number | null; change_pt?: number | null }
type KpiResponse = {
  kospi: KpiQuote
  kosdaq: KpiQuote
  usdkrw: KpiQuote
  vix: KpiQuote
  wti: KpiQuote
  gold: KpiQuote
  as_of?: string
  price_as_of?: string
  fetched_at?: string
}

type UniverseRow = {
  symbol: string
  display: string
  price?: number
  change?: number
  sector?: string
  market_cap?: number
  index_contribution_pt?: number
}
type UniverseResponse = { stocks?: UniverseRow[]; total?: number }

type LoadState = 'loading' | 'ready' | 'empty' | 'error'

/** KPI 카드 메타 */
const KPI_META: {
  key: keyof Omit<KpiResponse, 'as_of' | 'price_as_of' | 'fetched_at'>
  label: string
  suffix?: string
  digits: number
}[] = [
  { key: 'kospi', label: 'KOSPI', digits: 2 },
  { key: 'kosdaq', label: 'KOSDAQ', digits: 2 },
  { key: 'usdkrw', label: 'USD / KRW', suffix: '원', digits: 2 },
  { key: 'vix', label: 'VIX', digits: 2 },
  { key: 'wti', label: 'WTI', suffix: '$', digits: 2 },
  { key: 'gold', label: 'GOLD', suffix: '$', digits: 2 },
]

/** fetched_at(ISO) → 'HH:MM:SS' */
function fmtFetched(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  return d.toLocaleTimeString('ko-KR', { hour12: false })
}

/** 시세 신선도 라벨 */
function FreshnessLabel({ priceAsOf, fetchedAt }: { priceAsOf?: string | null; fetchedAt?: string | null }) {
  if (!priceAsOf && !fetchedAt) return null
  const when = fmtFetched(fetchedAt)
  return (
    <span className="font-mono text-[11px] text-muted">
      시세 {priceAsOf ?? '-'}
      {when && <> · {when} 조회</>}
    </span>
  )
}

/** ─── 페이지 로드 stagger ─── */
const container = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
}
const item = {
  hidden: { opacity: 0, y: 12 },
  show: { opacity: 1, y: 0, transition: { type: 'spring' as const, stiffness: 260, damping: 26 } },
}

/* ══════════════════════════ KPI 행 ══════════════════════════ */

function KpiRow({ apiBase }: { apiBase: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [data, setData] = useState<KpiResponse | null>(null)

  const load = useCallback((initial = false) => {
    if (initial) setState('loading')
    fetch(`${apiBase}/api/market/kpi`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: KpiResponse) => {
        setData(d)
        const anyValue = KPI_META.some(m => d?.[m.key]?.value != null)
        setState(anyValue ? 'ready' : 'empty')
      })
      .catch(() => setState(prev => (prev === 'ready' ? 'ready' : 'error'))) // 자동갱신 실패 시 직전값 유지
  }, [apiBase])

  useEffect(() => {
    load(true)
    const id = setInterval(() => load(false), 30_000) // 30초 자동 갱신
    return () => clearInterval(id)
  }, [load])

  if (state === 'loading') {
    return (
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        {KPI_META.map(m => (
          <div key={m.key} className="flex flex-col gap-3 rounded-card border border-line bg-card-2/40 p-4">
            <Skeleton className="h-3 w-16" />
            <Skeleton className="h-7 w-24" />
            <Skeleton className="h-4 w-14" />
          </div>
        ))}
      </div>
    )
  }

  if (state === 'error') {
    return (
      <ErrorState
        title="시장 지표를 불러오지 못했습니다"
        message="KPI 데이터 응답에 실패했습니다. 네트워크를 확인하고 다시 시도해 주세요."
        onRetry={load}
      />
    )
  }

  if (state === 'empty' || !data) {
    return (
      <EmptyState
        icon={<Activity size={20} strokeWidth={1.75} />}
        title="표시할 시장 지표가 없습니다"
        description="현재 KPI 값이 비어 있습니다. 장 시작 후 다시 확인해 주세요."
      />
    )
  }

  return (
    <div className="space-y-3">
      {(data.price_as_of || data.fetched_at) && (
        <div className="flex justify-end">
          <FreshnessLabel priceAsOf={data.price_as_of} fetchedAt={data.fetched_at} />
        </div>
      )}
      <motion.div
        variants={container}
        initial="hidden"
        animate="show"
        className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6"
      >
        {KPI_META.map((m, idx) => {
          const q = data[m.key]
          const value = q?.value ?? null
          const change = q?.change ?? null
          // 지수(kospi/kosdaq)는 포인트 변화도 함께 표기
          const changePt = (m.key === 'kospi' || m.key === 'kosdaq') ? (q?.change_pt ?? null) : undefined
          return (
            <motion.div key={m.key} variants={item}>
              <MetricCard
                label={m.label}
                value={value}
                change={change}
                changePt={changePt}
                suffix={m.suffix}
                digits={m.digits}
                primary={idx === 0}
              />
            </motion.div>
          )
        })}
      </motion.div>
    </div>
  )
}

/* ════════════════════════════════════════════════════════════
   전종목 Universe 검색 테이블 (TopStocks — 기존 완전 보존)
   ════════════════════════════════════════════════════════════ */
function TopStocks({ stocks, apiBase }: { stocks: Tick[]; apiBase: string }) {
  const [snapMeta, setSnapMeta] = useState<{ price_as_of?: string; fetched_at?: string }>({})
  const [query, setQuery] = useState('')
  const [displayRows, setDisplayRows] = useState<UniverseRow[]>([])
  const [sort, setSort] = useState<'contribution' | 'change' | 'market_cap'>('contribution')
  const [order, setOrder] = useState<'desc' | 'asc'>('desc')
  const [sector, setSector] = useState('')
  const [minMarketCap, setMinMarketCap] = useState('')
  const [direction, setDirection] = useState<'all' | 'up' | 'down'>('all')
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  useEffect(() => {
    let alive = true
    fetch(`${apiBase}/api/market/snapshot`)
      .then(r => (r.ok ? r.json() : Promise.reject()))
      .then((d: SnapshotResponse) => {
        if (!alive) return
        setSnapMeta({ price_as_of: d.price_as_of, fetched_at: d.fetched_at })
      })
      .catch(() => {})
    return () => { alive = false }
  }, [apiBase, refreshTrigger])

  // 15초마다 자동 갱신 타이머 실행
  useEffect(() => {
    const id = setInterval(() => {
      setRefreshTrigger(prev => prev + 1)
    }, 15_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const q = query.trim()
    const ctl = new AbortController()
    const t = window.setTimeout(() => {
      const params = new URLSearchParams({ q, limit: '20', sort, order, direction })
      if (sector) params.set('sector', sector)
      if (minMarketCap) params.set('min_market_cap', minMarketCap)
      fetch(`${apiBase}/api/market/universe?${params.toString()}`, { signal: ctl.signal })
        .then(r => (r.ok ? r.json() : Promise.reject()))
        .then((d: UniverseResponse) => { setDisplayRows(d.stocks ?? []) })
        .catch(() => { if (!ctl.signal.aborted) setDisplayRows([]) })
    }, 250)
    return () => { window.clearTimeout(t); ctl.abort() }
  }, [apiBase, query, sort, order, sector, minMarketCap, direction, refreshTrigger])

  const sectorOptions = Array.from(
    new Set([
      ...stocks.map(s => s.sector).filter(Boolean),
      ...displayRows.map(s => s.sector).filter(Boolean),
    ] as string[]),
  ).sort()

  const rawRows: UniverseRow[] =
    displayRows.length > 0
      ? displayRows
      : stocks.map(s => ({
          symbol: s.symbol,
          display: s.display,
          price: s.price,
          change: s.change,
          sector: s.sector,
        }))

  // 실시간 틱 데이터가 존재하면 실시간 가격 및 변동률 병합
  const tableRows: UniverseRow[] = rawRows.map(row => {
    const live = stocks.find(s => s.symbol === row.symbol)
    if (live) {
      return {
        ...row,
        price: live.price,
        change: live.change,
      }
    }
    return row
  })

  return (
    <Card
      eyebrow="Watchlist"
      title="전종목 유니버스"
      action={
        snapMeta.price_as_of || snapMeta.fetched_at ? (
          <FreshnessLabel priceAsOf={snapMeta.price_as_of} fetchedAt={snapMeta.fetched_at} />
        ) : undefined
      }
      noPadding
    >
      <div className="border-b border-line px-4 py-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-xs font-semibold text-beige">KOSPI 전종목 검색 · 필터 · 정렬</p>
            <p className="mt-0.5 text-[11px] text-muted">
              기여도는 pt 기준입니다. 검색·필터로 종목을 조회합니다.
            </p>
          </div>
          <input
            value={query}
            onChange={e => setQuery(e.target.value)}
            placeholder="종목명/코드/업종 검색"
            className="w-full rounded-chip border border-line bg-card-2 px-3 py-2 font-sans text-sm text-beige outline-none placeholder:text-muted focus:border-hanwha sm:w-64"
          />
        </div>
        <div className="mt-3 grid grid-cols-1 gap-2 md:grid-cols-5">
          <select
            value={sort}
            onChange={e => setSort(e.target.value as typeof sort)}
            className="rounded-chip border border-line bg-card-2 px-3 py-2 text-xs text-beige outline-none"
          >
            <option value="contribution">기여도순</option>
            <option value="change">등락률순</option>
            <option value="market_cap">시가총액순</option>
          </select>
          <select
            value={order}
            onChange={e => setOrder(e.target.value as typeof order)}
            className="rounded-chip border border-line bg-card-2 px-3 py-2 text-xs text-beige outline-none"
          >
            <option value="desc">내림차순</option>
            <option value="asc">오름차순</option>
          </select>
          <select
            value={direction}
            onChange={e => setDirection(e.target.value as typeof direction)}
            className="rounded-chip border border-line bg-card-2 px-3 py-2 text-xs text-beige outline-none"
          >
            <option value="all">전체 등락</option>
            <option value="up">상승만</option>
            <option value="down">하락만</option>
          </select>
          <select
            value={sector}
            onChange={e => setSector(e.target.value)}
            className="rounded-chip border border-line bg-card-2 px-3 py-2 text-xs text-beige outline-none"
          >
            <option value="">전체 섹터</option>
            {sectorOptions.map(s => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <input
            value={minMarketCap}
            onChange={e => setMinMarketCap(e.target.value.replace(/[^\d.]/g, ''))}
            placeholder="최소 시총"
            className="rounded-chip border border-line bg-card-2 px-3 py-2 text-xs text-beige outline-none placeholder:text-muted"
          />
        </div>
      </div>

      {tableRows.length === 0 ? (
        <EmptyState
          icon={<TrendingUp size={20} strokeWidth={1.75} />}
          title="종목 데이터 없음"
          description="현재 표시할 종목이 없습니다."
          className="m-5 border-0 bg-transparent px-0 py-6"
        />
      ) : (
        <div className="overflow-x-auto px-2 pb-3">
          <table className="w-full border-collapse">
            <thead>
              <tr className="border-b border-line text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
                <th className="px-3 py-2.5 text-left font-mono">종목</th>
                <th className="px-3 py-2.5 text-right font-mono">현재가</th>
                <th className="px-3 py-2.5 text-right font-mono">등락</th>
                <th className="px-3 py-2.5 text-right font-mono">시총</th>
                <th className="px-3 py-2.5 text-right font-mono">기여도</th>
              </tr>
            </thead>
            <tbody>
              {tableRows.map((s, i) => (
                <tr
                  key={s.symbol || s.display || i}
                  className="cursor-pointer border-b border-line/40 transition-colors last:border-0 hover:bg-card-2/40"
                  onClick={() => s.symbol && window.dispatchEvent(new CustomEvent('market:select-symbol', { detail: { code: s.symbol, name: s.display } }))}
                >
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium text-beige">{s.display}</span>
                      {s.sector && (
                        <span className="font-mono text-[10px] uppercase tracking-wide text-muted">
                          {s.sector}
                        </span>
                      )}
                    </div>
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-sm tabular-nums text-beige">
                    {s.price !== undefined ? s.price.toLocaleString('ko-KR') : '-'}
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <ChangePill value={s.change ?? 0} size="sm" />
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-muted">
                    {s.market_cap !== undefined ? s.market_cap.toLocaleString('ko-KR') : '-'}
                  </td>
                  <td className="px-3 py-2.5 text-right font-mono text-xs tabular-nums text-beige">
                    {s.index_contribution_pt !== undefined
                      ? `${s.index_contribution_pt.toFixed(3)}pt`
                      : '-'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

/* ════════════════════════════════════════════════════════════
   메인 — 2단 레이아웃 (좌: 메인 / 우: 사이드)
   ════════════════════════════════════════════════════════════ */
export function MarketDashboard({ ticks, apiBase }: { ticks: Tick[]; apiBase: string }) {
  const stocks = ticks.filter(t => t.asset_type === 'stock')

  // 종목/지수 선택 → 캔들 차트 연동. 하위 컴포넌트(테이블·Movers·히트맵·레이더)는 'market:select-symbol' CustomEvent 로 통신해 prop drilling 을 피한다.
  const [selected, setSelected] = useState<{ code: string; label: string }>({ code: '^KS11', label: 'KOSPI' })
  useEffect(() => {
    const onSelect = (e: Event) => {
      const d = (e as CustomEvent).detail as { code?: string; name?: string }
      if (d?.code) setSelected({ code: d.code, label: d.name || d.code })
    }
    window.addEventListener('market:select-symbol', onSelect)
    return () => window.removeEventListener('market:select-symbol', onSelect)
  }, [])

  return (
    <motion.div
      variants={container}
      initial="hidden"
      animate="show"
      className="space-y-6"
    >
      {/* ── 시장 현황 (KPI) ── */}
      <motion.section variants={item}>
        <SectionHeader
          eyebrow="Market Pulse"
          title="시장 현황"
          description="실시간 지수 · 환율 · 변동성 · 원자재 종합 지표"
        />
        <KpiRow apiBase={apiBase} />
      </motion.section>

      {/* ── 메인 · 좌측(히트맵 + 넓은 캔들 2/3) + 우측(시장폭 + 뉴스 1/3) ── */}
      <motion.div variants={item} className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-stretch">
        <div className="min-w-0 lg:col-span-2">
          <SectorTreemap apiBase={apiBase} />
        </div>
        <div className="min-w-0">
          <MarketRadar apiBase={apiBase} />
        </div>

        <div className="min-w-0 lg:col-span-2 [&>*]:h-full">
          <CandleChart symbol={selected.code} label={selected.label} apiBase={apiBase} />
        </div>
        <div className="min-w-0 [&>*]:h-full">
          <MarketNewsFlow
            apiBase={apiBase}
            feedMaxH={500}
            onStockClick={(code, name) => {
              window.dispatchEvent(new CustomEvent('atlas:navigate', {
                detail: { tab: 'idea', symbol: name, code },
              }))
            }}
          />
        </div>
      </motion.div>

      {/* ── 본문 · 좌측 2열(이슈·캘린더 / 위원회·브리핑) + 우측 채권·지수·FX(키 큰) ── */}
      <motion.div variants={item} className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:items-stretch">
        <div className="grid grid-cols-1 gap-6 md:grid-cols-2 md:items-stretch lg:col-span-2">
          <div className="h-full [&>*]:h-full">
            <Movers apiBase={apiBase} />
          </div>
          <div className="min-w-0 self-start">
            <EconomicCalendar />
          </div>
          <div className="h-full [&>*]:h-full">
            <CommitteeLatestWidget apiBase={apiBase} />
          </div>
          <div className="h-full [&>*]:h-full">
            <BriefingLatestWidget apiBase={apiBase} />
          </div>
        </div>
        <div className="min-w-0">
          <DataTable apiBase={apiBase} />
        </div>
      </motion.div>

      {/* ── 전종목 유니버스 — 풀폭(맨 아래) ── */}
      <motion.section variants={item}>
        <TopStocks stocks={stocks} apiBase={apiBase} />
      </motion.section>

    </motion.div>
  )
}


