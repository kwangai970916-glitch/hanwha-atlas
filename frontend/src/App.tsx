import { lazy, Suspense, useState, useEffect, useCallback, type ComponentType } from 'react'
import { motion } from 'framer-motion'
import { Header } from './components/Header'
import { cn } from './lib/utils'

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'
const TABS = [
  { id: 'market',    label: '시장현황',    sub: 'Live / Sector / Chart' },
  { id: 'pnl',      label: '손익현황',    sub: 'P&L / Holdings / News' },
  { id: 'briefing', label: '시황에이전트', sub: '장전 / 장중 / 장마감' },
  { id: 'idea',     label: 'AI 아이디어랩',  sub: 'Backtest / AI' },
  { id: 'committee', label: 'AI투자위원회', sub: '개별종목 심층리서치' },
] as const
type TabId = typeof TABS[number]['id']

const loadMarketDashboard = () =>
  import('./components/MarketDashboard').then((m) => ({ default: m.MarketDashboard }))
const loadPnlDashboard = () =>
  import('./components/PnlDashboard').then((m) => ({ default: m.PnlDashboard }))
const loadBriefingAgent = () =>
  import('./components/BriefingAgent').then((m) => ({ default: m.BriefingAgent }))
const loadIdeaLab = () => import('./components/IdeaLab').then((m) => ({ default: m.IdeaLab }))
const loadAICommittee = () =>
  import('./components/AICommittee').then((m) => ({ default: m.AICommittee }))

const MODULE_LOADERS: Record<TabId, () => Promise<{ default: ComponentType<any> }>> = {
  market: loadMarketDashboard,
  pnl: loadPnlDashboard,
  briefing: loadBriefingAgent,
  idea: loadIdeaLab,
  committee: loadAICommittee,
}

const MarketDashboard = lazy(loadMarketDashboard)
const PnlDashboard = lazy(loadPnlDashboard)
const BriefingAgent = lazy(loadBriefingAgent)
const IdeaLab = lazy(loadIdeaLab)
const AICommittee = lazy(loadAICommittee)
type MarketTick = {
  symbol: string
  display: string
  price: number
  value: number
  change: number
  asset_type: string
  sector?: string
}
type MarketStreamPayload = {
  ticks?: Array<{
    display?: string
    symbol: string
    price: number
    change: number
    asset_type?: string
    sector?: string
  }>
  as_of?: string
  fetched_at?: string
}
/** ATLAS 브랜드 마크 — 운용 데스크의 중심축/신호축 */
function BrandMark() {
  return (
    <svg width="30" height="30" viewBox="0 0 32 32" aria-hidden className="shrink-0">
      <circle cx="16" cy="16" r="10.5" fill="var(--hanwha)" fillOpacity="0.08" stroke="var(--hanwha)" strokeWidth="1.8" />
      <path d="M16 4.5 V27.5 M4.5 16 H27.5" stroke="var(--hanwha)" strokeWidth="1.7" strokeLinecap="round" />
      <path d="M9 23 L23 9" stroke="var(--beige)" strokeOpacity="0.55" strokeWidth="1.35" strokeLinecap="round" />
      <circle cx="16" cy="16" r="3.2" fill="var(--hanwha)" />
    </svg>
  )
}

function TabFallback({ label }: { label: string }) {
  return (
    <div className="rounded-card border border-line bg-card p-8 shadow-card">
      <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-hanwha">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-hanwha" />
        모듈 로드 중
      </div>
      <div className="font-display text-xl font-bold tracking-tight text-beige">{label}</div>
      <div className="mt-4 grid gap-3 md:grid-cols-3">
        <div className="h-24 animate-pulse rounded-card bg-card-2/60" />
        <div className="h-24 animate-pulse rounded-card bg-card-2/45" />
        <div className="h-24 animate-pulse rounded-card bg-card-2/30" />
      </div>
    </div>
  )
}

export default function App() {
  const [tab, setTab] = useState<TabId>('market')
  const [contentTab, setContentTab] = useState<TabId>('market')
  const [committeeTicker, setCommitteeTicker] = useState<string>('')
  const [ticks, setTicks] = useState<MarketTick[]>([])
  const [streamState, setStreamState] = useState<'connecting' | 'open' | 'error'>('connecting')
  const [streamError, setStreamError] = useState<string | null>(null)
  const [streamKey, setStreamKey] = useState(0)
  const [marketAsOf, setMarketAsOf] = useState<string | undefined>()

  // 영웅흐름(원클릭): 보유종목 → Drawer '위원회 소집' → committee 탭 전환 + 프리셋 자동실행
  const goToCommittee = useCallback((ticker: string) => {
    setCommitteeTicker(ticker)
    setTab('committee')
  }, [])

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => setContentTab(tab))
    return () => window.cancelAnimationFrame(raf)
  }, [tab])

  useEffect(() => {
    // 첫 화면 안정 후 나머지 탭 chunk를 백그라운드 프리로드해 이후 전환을 즉시화.
    const preload = () => {
      TABS.forEach((t) => {
        if (t.id !== 'market') MODULE_LOADERS[t.id]().catch(() => undefined)
      })
    }
    const ric = window.requestIdleCallback?.(preload, { timeout: 1600 })
    const timer = window.setTimeout(preload, 1800)
    return () => {
      if (ric != null) window.cancelIdleCallback?.(ric)
      window.clearTimeout(timer)
    }
  }, [])

  const switchTab = useCallback((next: TabId) => {
    if (next === tab) return
    // 탭 하이라이트는 즉시 바꾸고, 무거운 모듈 마운트는 다음 프레임으로 미뤄 클릭 반응성을 보장.
    setTab(next)
  }, [tab])

  useEffect(() => {
    let closedByReact = false
    setStreamState('connecting')
    setStreamError(null)
    const es = new EventSource(`${API_BASE}/api/market/stream`)
    es.onopen = () => {
      if (closedByReact) return
      setStreamState('open')
      setStreamError(null)
    }
    es.onmessage = (e) => {
      try {
        const d = JSON.parse(e.data) as MarketStreamPayload
        const next = (d.ticks ?? []).map((t) => ({
          symbol: t.symbol,
          display: t.display ?? t.symbol,
          price: t.price,
          value: t.price,
          change: t.change,
          asset_type: t.asset_type ?? 'index',
          sector: t.sector,
        }))
        setStreamState('open')
        setStreamError(null)
        setMarketAsOf(d.as_of ?? d.fetched_at)
        // 일시적인 provider 실패로 빈 ticks가 와도 기존 테이프를 지우지 않는다.
        if (next.length > 0) setTicks(next)
      } catch (err) {
        setStreamState('error')
        setStreamError(err instanceof Error ? err.message : '시세 스트림 파싱 오류')
      }
    }
    es.onerror = () => {
      if (closedByReact) return
      // EventSource는 자동 재연결한다. UI는 "IDLE" 대신 재연결 중임을 명확히 표시한다.
      setStreamState('error')
      setStreamError('시세 스트림 재연결 중…')
    }
    return () => {
      closedByReact = true
      es.close()
    }
  }, [streamKey])

  return (
    <div className="min-h-screen bg-bg">
      {/* 상단 브랜드바 + 라이브 테이프 (sticky) */}
      <motion.header
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3 }}
        className="sticky top-0 z-50 border-b border-line bg-card/80 backdrop-blur-xl"
      >
        <div className="flex h-14 items-center gap-3 px-6">
          <BrandMark />
          <div className="flex items-baseline gap-3">
            <span className="font-display text-[22px] font-bold tracking-[0.06em] text-hanwha">
              ATLAS
            </span>
            <span className="font-mono text-[10px] font-medium uppercase tracking-[0.14em] text-muted">
              Agentic · Trading · Live · Analytics · System
            </span>
          </div>
        </div>
        <Header
          ticks={ticks}
          loading={streamState === 'connecting' && ticks.length === 0}
          error={streamState === 'error' ? streamError : null}
          onRetry={() => setStreamKey((key) => key + 1)}
          asOf={marketAsOf}
        />
      </motion.header>

      {/* 탭 네비 (액티브 = 오렌지 인디케이터) */}
      <nav role="tablist" aria-label="주요 메뉴" className="sticky top-[92px] z-40 flex gap-1 overflow-x-auto border-b border-line bg-bg/85 px-6 backdrop-blur-xl">
        {TABS.map((t) => {
          const active = tab === t.id
          return (
            <button
              key={t.id}
              role="tab"
              aria-selected={active}
              aria-controls={`tabpanel-${t.id}`}
              onClick={() => switchTab(t.id)}
              onMouseEnter={() => MODULE_LOADERS[t.id]().catch(() => undefined)}
              onFocus={() => MODULE_LOADERS[t.id]().catch(() => undefined)}
              className={cn(
                'relative flex shrink-0 flex-col items-start px-4 py-3 text-left transition-colors',
                active ? 'text-hanwha' : 'text-muted hover:text-beige',
              )}
            >
              <span className="text-sm font-bold tracking-tight">{t.label}</span>
              <span className="mt-0.5 font-mono text-[10px] uppercase tracking-[0.04em] opacity-70">
                {t.sub}
              </span>
              {active && (
                <motion.span
                  layoutId="tab-indicator"
                  className="absolute inset-x-2 -bottom-px h-0.5 rounded-full bg-hanwha"
                  transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                />
              )}
            </button>
          )
        })}
      </nav>

      {/* 탭 콘텐츠: exit 애니메이션 대기 제거 + lazy chunk + 다음 프레임 마운트 */}
      <main className="mx-auto max-w-[1480px] p-6">
        <Suspense fallback={<TabFallback label={TABS.find((t) => t.id === tab)?.label ?? '모듈'} />}>
          <motion.div
            key={contentTab}
            role="tabpanel"
            id={`tabpanel-${contentTab}`}
            initial={{ opacity: 0.92 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.08 }}
          >
            {contentTab === 'market'    && <MarketDashboard ticks={ticks} apiBase={API_BASE} />}
            {contentTab === 'pnl'       && <PnlDashboard apiBase={API_BASE} goToCommittee={goToCommittee} />}
            {contentTab === 'briefing'  && <BriefingAgent apiBase={API_BASE} />}
            {contentTab === 'idea'      && <IdeaLab apiBase={API_BASE} />}
            {contentTab === 'committee' && <AICommittee apiBase={API_BASE} presetTicker={committeeTicker} />}
          </motion.div>
        </Suspense>
      </main>

      {import.meta.env.VITE_OFFLINE === '1' && (
        <div className="fixed right-3 top-3 z-[9999] flex items-center gap-1.5 rounded-full border border-hanwha/40 bg-canvas/90 px-3 py-1 font-mono text-[11px] font-semibold text-hanwha shadow-glow backdrop-blur">
          <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-hanwha" />
          제출용 · 오프라인 모드 · 데이터 기준 2026-06-09
        </div>
      )}
    </div>
  )
}
