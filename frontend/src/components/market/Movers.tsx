/**
 * Movers — 거래대금 상위 / 급등 / 급락 종목 위젯
 *
 * - 탭 3개: 거래대금 상위 · 급등 · 급락
 * - 이상치 캡: |change| > 31% 행 제외 (상·하한 30% 초과는 노이즈)
 * - 거래대금: 조/억 단위 포맷
 * - 각 행: 종목명 · 등락pill · 값
 * - 로딩 / 빈 / 에러 3종
 */
import { useCallback, useEffect, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Flame, TrendingUp, TrendingDown, Zap } from 'lucide-react'
import { Card, ChangePill, Badge, Skeleton, EmptyState, ErrorState } from '../ui'

/* ── 타입 ── */
type UniverseRow = {
  symbol: string
  display: string
  price?: number
  change?: number
  sector?: string
  market_cap?: number
  index_contribution_pt?: number
  trade_value?: number
  trade_value_estimated?: boolean
  volume?: number
}
type UniverseResponse = { stocks?: UniverseRow[]; total?: number }
type LoadState = 'loading' | 'ready' | 'empty' | 'error'
type TabId = 'trade_value' | 'gainer' | 'loser'

/* ── 거래대금 포맷 ── */
function fmtTradeValue(v: number | undefined): string {
  if (v === undefined || v === null) return '—'
  if (v >= 1e12) return `${(v / 1e12).toFixed(2)}조`
  if (v >= 1e8) return `${(v / 1e8).toFixed(0)}억`
  if (v >= 1e4) return `${(v / 1e4).toFixed(0)}만`
  return v.toLocaleString('ko-KR')
}

/* ── 탭 정의 ── */
const TABS: { id: TabId; label: string; icon: React.ReactNode }[] = [
  { id: 'trade_value', label: '거래대금', icon: <Flame size={11} /> },
  { id: 'gainer', label: '급등', icon: <TrendingUp size={11} /> },
  { id: 'loser', label: '급락', icon: <TrendingDown size={11} /> },
]

/* ── 이상치 캡 ── */
const CHANGE_CAP = 31

function filterOutliers(stocks: UniverseRow[]): UniverseRow[] {
  return stocks.filter(s => Math.abs(s.change ?? 0) <= CHANGE_CAP)
}

/* ── 종목 행 ── */
function MoverRow({
  stock,
  rank,
  tab,
}: {
  stock: UniverseRow
  rank: number
  tab: TabId
}) {
  const change = stock.change ?? 0
  const isUp = change >= 0

  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: rank * 0.04, type: 'spring', stiffness: 300, damping: 28 }}
      className="flex items-center gap-2.5 py-2 border-b border-line/30 last:border-0 cursor-pointer hover:bg-card-2/40 rounded px-1 -mx-1"
      onClick={() => stock.symbol && window.dispatchEvent(new CustomEvent('market:select-symbol', { detail: { code: stock.symbol, name: stock.display } }))}
    >
      {/* 랭크 번호 */}
      <span
        className={`font-mono text-[10px] tabular-nums w-4 text-right shrink-0 ${
          rank === 0 ? 'text-hanwha font-bold' : 'text-muted'
        }`}
      >
        {rank + 1}
      </span>

      {/* 종목명 */}
      <div className="flex-1 min-w-0">
        <p className="truncate text-xs font-semibold text-beige">{stock.display}</p>
        {stock.sector && (
          <p className="truncate font-mono text-[9px] uppercase tracking-wide text-muted">
            {stock.sector}
          </p>
        )}
      </div>

      {/* 값 (탭에 따라 다름) */}
      <div className="flex items-center gap-2 shrink-0">
        {tab === 'trade_value' && (
          <span className="font-mono text-xs tabular-nums text-greige">
            {stock.trade_value_estimated && <span className="mr-0.5 text-muted" title="거래량×현재가 추정">~</span>}
            {fmtTradeValue(stock.trade_value)}
          </span>
        )}

        {tab === 'gainer' && stock.price !== undefined && (
          <span className="font-mono text-xs tabular-nums text-muted">
            {stock.price.toLocaleString('ko-KR')}
          </span>
        )}

        {tab === 'loser' && stock.price !== undefined && (
          <span className="font-mono text-xs tabular-nums text-muted">
            {stock.price.toLocaleString('ko-KR')}
          </span>
        )}

        <ChangePill value={change} size="sm" />
      </div>
    </motion.div>
  )
}

/* ── 메인 컴포넌트 ── */
export function Movers({ apiBase }: { apiBase: string }) {
  const [activeTab, setActiveTab] = useState<TabId>('trade_value')
  const [states, setStates] = useState<Record<TabId, LoadState>>({
    trade_value: 'loading',
    gainer: 'loading',
    loser: 'loading',
  })
  const [data, setData] = useState<Record<TabId, UniverseRow[]>>({
    trade_value: [],
    gainer: [],
    loser: [],
  })

  const loadTab = useCallback(
    (tab: TabId, silent = false) => {
      if (!silent) setStates(prev => ({ ...prev, [tab]: 'loading' }))

      const params = new URLSearchParams({ limit: '10', sort: 'trade_value', order: 'desc' })

      if (tab === 'trade_value') {
        params.set('sort', 'trade_value')
        params.set('order', 'desc')
        params.set('direction', 'all')
      } else if (tab === 'gainer') {
        params.set('sort', 'change')
        params.set('order', 'desc')
        params.set('direction', 'up')
      } else {
        params.set('sort', 'change')
        params.set('order', 'asc')
        params.set('direction', 'down')
      }

      fetch(`${apiBase}/api/market/universe?${params.toString()}`)
        .then(r => {
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          return r.json() as Promise<UniverseResponse>
        })
        .then(d => {
          const filtered = filterOutliers(d.stocks ?? [])
          setData(prev => ({ ...prev, [tab]: filtered }))
          setStates(prev => ({
            ...prev,
            [tab]: filtered.length > 0 ? 'ready' : 'empty',
          }))
        })
        .catch(() => {
          setStates(prev => ({ ...prev, [tab]: 'error' }))
        })
    },
    [apiBase],
  )

  useEffect(() => {
    loadTab('trade_value')
    loadTab('gainer')
    loadTab('loser')
    // 60초 자동 갱신(조용히 — 스켈레톤 깜빡임 없이)
    const id = setInterval(() => {
      loadTab('trade_value', true)
      loadTab('gainer', true)
      loadTab('loser', true)
    }, 60_000)
    return () => clearInterval(id)
  }, [loadTab])

  const currentState = states[activeTab]
  const currentData = data[activeTab]

  return (
    <Card
      eyebrow="Movers"
      title="이슈 종목"
      action={
        <Badge tone="hanwha" dot>
          <Zap size={9} />
          Live
        </Badge>
      }
      noPadding
    >
      {/* 탭 바 */}
      <div className="flex border-b border-line px-4 pt-1 gap-0">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`
              relative flex items-center gap-1.5 px-3 py-2.5 text-[11px] font-semibold
              transition-colors duration-150 focus:outline-none
              ${
                activeTab === tab.id
                  ? 'text-beige'
                  : 'text-muted hover:text-greige'
              }
            `}
          >
            <span className={activeTab === tab.id ? 'text-hanwha' : 'text-muted'}>
              {tab.icon}
            </span>
            {tab.label}
            {activeTab === tab.id && (
              <motion.div
                layoutId="movers-tab-indicator"
                className="absolute bottom-0 left-0 right-0 h-0.5 bg-hanwha rounded-full"
                transition={{ type: 'spring', stiffness: 400, damping: 30 }}
              />
            )}
          </button>
        ))}
      </div>

      {/* 콘텐츠 */}
      <div className="px-4 py-3 min-h-[280px]">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
          >
            {currentState === 'loading' && (
              <div className="space-y-2.5 pt-1">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="flex items-center gap-2.5">
                    <Skeleton className="h-3 w-4" />
                    <Skeleton className="h-3 flex-1" />
                    <Skeleton className="h-5 w-16 rounded-pill" />
                  </div>
                ))}
              </div>
            )}

            {currentState === 'error' && (
              <ErrorState
                title="데이터 로드 실패"
                message="종목 데이터를 불러오지 못했습니다."
                onRetry={() => loadTab(activeTab)}
                className="border-0 bg-transparent py-8"
              />
            )}

            {currentState === 'empty' && (
              <EmptyState
                icon={<TrendingUp size={18} strokeWidth={1.75} />}
                title="표시할 종목 없음"
                description="현재 조건에 맞는 종목이 없습니다."
                className="border-0 bg-transparent py-8"
              />
            )}

            {currentState === 'ready' && (
              <div>
                {currentData.map((s, i) => (
                  <MoverRow key={s.symbol || i} stock={s} rank={i} tab={activeTab} />
                ))}
              </div>
            )}
          </motion.div>
        </AnimatePresence>
      </div>
    </Card>
  )
}

export default Movers
