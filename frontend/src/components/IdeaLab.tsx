import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import {
  Activity,
  ArrowDownToDot,
  CheckCircle2,
  Clock,
  Gavel,
  GitBranch,
  MessagesSquare,
  Newspaper,
  ShieldAlert,
  Target,
  Users,
} from 'lucide-react'
import { Badge, Card, EmptyState, ErrorState, SectionHeader, Spinner, Stat } from './ui'
import { cn } from '../lib/utils'
import { LiveFeed, type AgentMessage } from './committee/LiveFeed'

type Holding = { name: string; code: string }
type AsyncState = 'idle' | 'loading' | 'error' | 'done'
type FactorScores = Record<string, number>

type NewsFlowItem = {
  title?: string
  source?: string
  published_at?: string | null
  symbols?: Array<string | undefined>
  stage?: string
}

type TimingSignal = {
  signal?: 'enter' | 'wait' | 'avoid'
  rsi?: number | null
  ma20_pct?: number | null
  reason?: string | null
}

type MacroFlow = {
  label?: string
  score?: number
  summary?: string
  keywords?: string[]
  signals?: string[]
  source?: string
}

type SectorFlow = {
  sector?: string
  theme?: string
  score?: number
  news_score?: number
  change?: number | null
  foreign_flow?: 'buy' | 'sell' | 'neutral'
  macro_tags?: string[]
  why?: string
  representatives?: Array<{ symbol: string; name: string; score: number }>
}

type StockCandidate = {
  symbol: string
  name: string
  sector: string
  theme: string
  score: number
  discovery_score?: number
  conviction_score?: number
  timing_signal?: TimingSignal
  route?: string[]
  why_now?: string
  thesis?: string
  factor_scores?: FactorScores
  evidence_source?: string
  evidence?: Array<NewsFlowItem | { title?: string; detail?: string; claim?: string; source?: string; value?: unknown }>
}

type RadarPick = StockCandidate & {
  pick_id?: string
  horizon_months?: number
  counter_evidence?: string[]
  checklist?: string[]
  actions?: string[]
}

type RadarResponse = {
  generated_at: string
  horizon_months: number
  keywords?: string
  engine?: string
  macro_flow?: MacroFlow
  sector_flow?: SectorFlow[]
  stock_candidates?: StockCandidate[]
  news_flow?: NewsFlowItem[]
  committee_minutes?: Array<{ agent?: string; stage?: string; text?: string; source?: string; icon?: string }>
  pipeline?: { summary?: string; stages?: string[] }
  market_regime?: { label?: string; summary?: string; news_keywords?: string[]; macro_points?: string[]; source?: string; vkospi?: number | null }
  themes?: Array<{ theme: string; sector: string; score: number; macro_tags?: string[]; commentary?: string }>
  top_picks?: RadarPick[]
  data_quality?: { mode?: string; regime_source?: string; warnings?: string[] }
}

type CommitteePhase = (typeof IDEATION_PIPELINE)[number]

const FACTOR_LABEL: Record<string, string> = {
  chart: '가격/차트',
  supply_demand: '수급',
  news: '뉴스',
  macro: '매크로',
  valuation: '밸류',
  risk: '리스크',
}


const inputBase = 'w-full rounded-chip border border-line bg-canvas px-3.5 py-2.5 text-sm text-beige placeholder:text-muted/70 transition-colors focus:border-hanwha focus:outline-none focus:ring-1 focus:ring-hanwha/40'
const buttonBase = 'inline-flex items-center justify-center gap-2 rounded-chip px-4 py-2.5 text-sm font-semibold transition-all disabled:cursor-not-allowed disabled:opacity-50'

const IDEATION_PIPELINE: ReadonlyArray<{
  key: string
  label: string
  icon: ReactNode
  agents: string[]
  image: string
  summary: string
}> = [
  {
    key: 'research',
    label: '뉴스·매크로 조사',
    icon: <Newspaper size={15} />,
    agents: ['뉴스 큐레이터', 'Macro PM', '이벤트 태거'],
    image: '/illustrations/process/committee-research-agent.png',
    summary: '뉴스 이벤트와 금리·환율·지수 환경을 한 번에 읽고 회의 아젠다를 만듭니다.',
  },
  {
    key: 'sector_debate',
    label: '섹터 라운드테이블',
    icon: <MessagesSquare size={15} />,
    agents: ['섹터 애널리스트', 'Bull 리서처', 'Bear 리서처'],
    image: '/illustrations/process/committee-debate-agent.png',
    summary: '수혜 섹터와 과열 섹터를 나눠 토론하고 Macro → Sector 경로를 좁힙니다.',
  },
  {
    key: 'risk_review',
    label: '리스크 사전심의',
    icon: <ShieldAlert size={15} />,
    agents: ['리스크 매니저', '수급 추적', '타이밍 감시'],
    image: '/illustrations/process/committee-risk-agent.png',
    summary: '뉴스 모멘텀만 보지 않고 변동성·수급·진입 타이밍을 반대 관점에서 검증합니다.',
  },
  {
    key: 'decision',
    label: 'PM 의장 합의·제안',
    icon: <Gavel size={15} />,
    agents: ['PM 의장', 'Stock Picker', '아이디어 기록관'],
    image: '/illustrations/process/committee-decision-agent.png',
    summary: 'AI가 회의록을 정리하고 점수·근거·체크리스트를 취합하여 최종 포지션 편입 후보군을 합의 및 제안합니다.',
  },
]

// 백엔드 위원회 stage → 4단계 진행카드 인덱스 매핑 (5 stage → 4 phase)
const STAGE_TO_PHASE: Record<string, number> = {
  starting: 0, discovery: 0, sector_debate: 1, nomination: 2, risk_review: 2, decision: 3, done: 3,
}

function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="mb-1.5 block font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">{children}</span>
}

function PrimaryButton({ children, onClick, disabled, loading, icon }: { children: ReactNode; onClick: () => void; disabled?: boolean; loading?: boolean; icon?: ReactNode }) {
  return (
    <button onClick={onClick} disabled={disabled} className={cn(buttonBase, 'bg-hanwha text-canvas shadow-glow hover:bg-hanwha-2')}>
      {loading ? <Spinner size={15} className="text-canvas" /> : icon}
      {children}
    </button>
  )
}

function flowTone(signal?: string) {
  if (signal === 'avoid') return 'down'
  if (signal === 'wait') return 'neutral'
  return 'up'
}

export function IdeaLab({ apiBase }: { apiBase: string; holdings?: Holding[] }) {
  const [keywords, setKeywords] = useState('')
  const [radar, setRadar] = useState<RadarResponse | null>(null)
  const [radarState, setRadarState] = useState<AsyncState>('idle')
  const [radarError, setRadarError] = useState('')
  const [activePhase, setActivePhase] = useState(0)
  const [selectedCandidate, setSelectedCandidate] = useState<StockCandidate | RadarPick | null>(null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [autoLoadFailed, setAutoLoadFailed] = useState(false)
  const pollRef = useRef<number | null>(null)
  const msgRef = useRef<number | null>(null)
  const sinceRef = useRef(0)
  const feedBottomRef = useRef<HTMLDivElement | null>(null)
  const autoloadedRef = useRef(false)

  const stopTimers = useCallback(() => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    if (msgRef.current) window.clearInterval(msgRef.current)
    pollRef.current = null
    msgRef.current = null
  }, [])

  // 언마운트 시 폴링 타이머 정리
  useEffect(() => () => stopTimers(), [stopTimers])

  // radar 동기 호출 → 실제 멀티에이전트 위원회 비동기 job 폴링으로 전환.
  // 결과(decision.json)는 RadarResponse 상위호환이라 아래 결과 컴포넌트는 그대로 동작한다.
  const runRadar = useCallback(async () => {
    setRadarState('loading')
    setRadarError('')
    setActivePhase(0)
    setSelectedCandidate(null)
    setRadar(null)
    setMessages([])
    sinceRef.current = 0
    stopTimers()
    autoloadedRef.current = true
    try {
      const params = new URLSearchParams({ horizon_months: '3' })
      if (keywords.trim()) params.set('keywords', keywords.trim())
      const r = await fetch(`${apiBase}/api/idea/committee/run?${params.toString()}`, { method: 'POST' })
      if (!r.ok) throw new Error(`Committee request failed: ${r.status}`)
      const { job_id } = await r.json()
      if (!job_id) throw new Error('작업 ID를 받지 못했습니다.')

      // 에이전트 발언 스트림 폴링 (2초)
      msgRef.current = window.setInterval(async () => {
        try {
          const md = await fetch(`${apiBase}/api/idea/committee/messages/${job_id}?since=${sinceRef.current}`).then(x => x.json())
          if (md.messages?.length) {
            setMessages(prev => [...prev, ...md.messages])
            sinceRef.current = md.messages[md.messages.length - 1].idx + 1
            setTimeout(() => feedBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
          }
        } catch { /* best-effort */ }
      }, 2000)

      // 단계 상태 폴링 (5초) — 실제 stage가 4단계 진행카드를 구동
      pollRef.current = window.setInterval(async () => {
        try {
          const s = await fetch(`${apiBase}/api/idea/committee/status?job_id=${job_id}`).then(x => x.json())
          if (typeof s.stage === 'string' && s.stage in STAGE_TO_PHASE) setActivePhase(STAGE_TO_PHASE[s.stage])
          if (s.stage === 'done') {
            stopTimers()
            const d: RadarResponse = await fetch(`${apiBase}/api/idea/committee/result?job_id=${job_id}`).then(x => x.json())
            setRadar(d)
            const nextCandidates = d.stock_candidates?.length ? d.stock_candidates : d.top_picks ?? []
            setSelectedCandidate(nextCandidates[0] ?? null)
            setRadarState('done')
            setActivePhase(IDEATION_PIPELINE.length - 1)
          } else if (s.stage === 'error' || s.stage === 'unknown') {
            stopTimers()
            setRadarError(s.error ?? '아이디에이션 회의 실행 실패')
            setRadarState('error')
            setActivePhase(0)
          }
        } catch (e) {
          stopTimers()
          setRadarError(e instanceof Error ? e.message : '상태 조회 실패')
          setRadarState('error')
          setActivePhase(0)
        }
      }, 5000)
    } catch (e) {
      stopTimers()
      setRadar(null)
      setSelectedCandidate(null)
      setRadarError(e instanceof Error ? e.message : '아이디에이션 회의 실행 실패')
      setRadarState('error')
      setActivePhase(0)
    }
  }, [apiBase, keywords, stopTimers])

  // 데모 안전망: 미리 생성된 최근 위원회 결과(/latest, seed 폴백)를 즉시 로드.
  // 라이브 실행(수 분) 없이 실제 회의 결과를 0초에 보여준다.
  const loadLatest = useCallback(async () => {
    setRadarState('loading')
    setRadarError('')
    stopTimers()
    autoloadedRef.current = true
    setMessages([])
    setSelectedCandidate(null)
    try {
      const d: RadarResponse & { available?: boolean } = await fetch(`${apiBase}/api/idea/committee/latest`).then(x => x.json())
      const next = d.stock_candidates?.length ? d.stock_candidates : d.top_picks ?? []
      if (d.available === false || !next.length) {
        throw new Error('저장된 최근 회의 결과가 없습니다. [회의 시작]으로 새로 실행하세요.')
      }
      setRadar(d)
      setSelectedCandidate(next[0] ?? null)
      setRadarState('done')
      setActivePhase(IDEATION_PIPELINE.length - 1)
    } catch (e) {
      setRadar(null)
      setSelectedCandidate(null)
      setRadarError(e instanceof Error ? e.message : '최근 결과 로드 실패')
      setRadarState('error')
    }
  }, [apiBase, stopTimers])

  // 마운트 시 최근 위원회 결과 자동 로드 (데모 지속성). 사용자가 실행을 시작하면 건너뛰고, 실패 시 안내 플래그를 세운다.
  useEffect(() => {
    if (typeof fetch !== 'function') return
    let cancelled = false
    fetch(`${apiBase}/api/idea/committee/latest`)
      .then(x => x.json())
      .then((d: RadarResponse & { available?: boolean }) => {
        if (cancelled || autoloadedRef.current) return
        const next = d?.stock_candidates?.length ? d.stock_candidates : d?.top_picks ?? []
        if (d?.available === false || !next.length) {
          if (!cancelled) setAutoLoadFailed(true)
          return
        }
        setRadar(d)
        setSelectedCandidate(next[0] ?? null)
        setRadarState('done')
        setActivePhase(IDEATION_PIPELINE.length - 1)
      })
      .catch(() => { if (!cancelled) setAutoLoadFailed(true) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase])

  const candidates = radar?.stock_candidates?.length ? radar.stock_candidates : radar?.top_picks ?? []

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-7">
      <SectionHeader
        eyebrow="Idea Lab"
        title="AI 아이디에이션 회의"
        description="서브에이전트들이 뉴스 플로우를 읽고 Macro → Sector → Stock 순서로 토론해 투자 후보를 상정합니다."
      />

      <Card
        eyebrow="Convene"
        title="아이디에이션 회의 소집"
        action={<Badge tone="hanwha" dot>{radarState === 'loading' ? 'AI in session' : 'LLM · AI'}</Badge>}
      >
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-[1fr_auto] lg:items-end">
          <label>
            <FieldLabel>회의 아젠다 / 뉴스 키워드</FieldLabel>
            <input value={keywords} onChange={e => setKeywords(e.target.value)} className={inputBase} placeholder="예: AI 반도체, 전력망, 방산, 조선 — 비워두면 전체 뉴스 플로우" />
          </label>
          <div className="flex gap-2">
            <PrimaryButton onClick={runRadar} disabled={radarState === 'loading'} loading={radarState === 'loading'} icon={<Users size={15} />}>{radarState === 'loading' ? 'AI 실행 중' : '회의 시작'}</PrimaryButton>
            <button type="button" onClick={loadLatest} disabled={radarState === 'loading'} className={cn(buttonBase, 'border border-hanwha/35 bg-hanwha/[0.06] text-greige hover:border-hanwha/55 hover:text-beige')}>
              <Clock size={14} />
              최근 결과
              <span className="font-mono text-[10px] text-muted">즉시 보기</span>
            </button>
          </div>
        </div>
        {radarState === 'error' && <div className="mt-5"><ErrorState title="아이디에이션 회의 실패" message={radarError} onRetry={runRadar} /></div>}
        {autoLoadFailed && radarState === 'idle' && (
          <p className="mt-3 text-xs text-muted">
            이전 회의 결과가 없습니다. <span className="text-hanwha">[회의 시작]</span>을 눌러 바로 실행해 보세요.
          </p>
        )}
        {!autoLoadFailed && (
          <p className="mt-3 text-xs text-muted">
            자동 시작은 꺼져 있습니다. 회의 시작을 누르면 AI 기반 서브에이전트 회의가 뉴스·매크로·섹터·리스크·종목 후보를 압축합니다.
          </p>
        )}
      </Card>

      <IdeationWorkflow state={radarState} activePhase={activePhase} radar={radar} />

      {radarState === 'loading' && (
        <Card eyebrow="Live Feed" title="에이전트 실시간 발언" action={<Badge tone="hanwha" dot>LIVE</Badge>}>
          <LiveFeed messages={messages} feedBottomRef={feedBottomRef} emptyLabel="에이전트 소집 중 — 첫 발언을 기다리는 중입니다…" />
        </Card>
      )}

      {radar ? (
        <div className="space-y-6">
          <PipelineOverview radar={radar} />
          <CommitteeMinutes radar={radar} />
          <SectorFlowBoard sectors={radar.sector_flow ?? []} />
          <CandidateBoard
            candidates={candidates}
            selectedSymbol={selectedCandidate?.symbol}
            onSelect={setSelectedCandidate}
          />
          <CandidateDecisionReport pick={selectedCandidate} radar={radar} />
          <NewsTape news={radar.news_flow ?? []} />
        </div>
      ) : null}

    </motion.div>
  )
}

function IdeationWorkflow({ state, activePhase, radar }: { state: AsyncState; activePhase: number; radar: RadarResponse | null }) {
  const current = IDEATION_PIPELINE[Math.min(activePhase, IDEATION_PIPELINE.length - 1)]
  return (
    <Card
      eyebrow="AI Committee Workflow"
      title="AI 서브에이전트 회의 진행"
      action={<Badge tone={state === 'loading' ? 'hanwha' : state === 'done' ? 'up' : 'neutral'} dot>{state === 'loading' ? current.label : state === 'done' ? 'AI minutes ready' : 'Waiting'}</Badge>}
      noPadding
    >
      <div className="p-5">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {IDEATION_PIPELINE.map((phase, idx) => {
            const active = state === 'loading' && idx === activePhase
            const done = state === 'done' || (state === 'loading' && idx < activePhase)
            return <IdeationPhaseCard key={phase.key} phase={phase} index={idx + 1} active={active} done={done} />
          })}
        </div>
      </div>
    </Card>
  )
}

function IdeationPhaseCard({ phase, index, active, done }: { phase: CommitteePhase; index: number; active: boolean; done: boolean }) {
  const reduce = useReducedMotion()
  return (
    <motion.article
      animate={active && !reduce ? { y: [0, -3, 0] } : { y: 0 }}
      transition={active && !reduce ? { repeat: Infinity, duration: 2.2, ease: 'easeInOut' } : {}}
      className={cn(
        'relative overflow-hidden rounded-card border p-4 transition-colors',
        active ? 'border-hanwha/55 bg-hanwha/[0.06] shadow-glow' : done ? 'border-hanwha/30 bg-card-2/40' : 'border-line bg-canvas/40',
      )}
    >
      {active && (
        <motion.span
          className="absolute inset-x-0 top-0 h-0.5 bg-hanwha"
          animate={reduce ? { scaleX: 1, originX: 0 } : { scaleX: [0, 1, 0], originX: [0, 0, 1] }}
          transition={reduce ? {} : { duration: 2.2, ease: 'easeInOut', repeat: Infinity }}
        />
      )}
      <div className="mb-2.5 flex items-center justify-between">
        <span
          className={cn(
            'grid h-8 w-8 place-items-center rounded-pill transition-colors',
            active ? 'bg-hanwha/15 text-hanwha' : done ? 'bg-up/12 text-up' : 'bg-card-2 text-muted',
          )}
        >
          {done ? <CheckCircle2 size={15} /> : active ? <Spinner size={15} /> : phase.icon}
        </span>
        <span className="font-mono text-[11px] font-semibold tabular-nums text-muted">
          {String(index).padStart(2, '0')}/04
        </span>
      </div>
      <div className="relative mb-3 grid h-40 place-items-center overflow-hidden rounded-card bg-card/30 px-1 pb-4 pt-2">
        {active && (
          <motion.span
            className="absolute inset-x-5 bottom-2 h-px rounded-full bg-hanwha/80"
            animate={reduce ? { scaleX: 1, opacity: 1 } : { scaleX: [0.15, 1, 0.15], opacity: [0.35, 1, 0.35] }}
            transition={reduce ? {} : { repeat: Infinity, duration: 1.8, ease: 'easeInOut' }}
          />
        )}
        <motion.img
          src={phase.image}
          alt=""
          aria-hidden="true"
          loading="lazy"
          decoding="async"
          className={cn(
            'h-[150px] w-full object-contain object-center transition-opacity',
            !done && !active && 'opacity-35 grayscale',
          )}
          animate={active && !reduce ? { scale: [1, 1.045, 1] } : { scale: 1 }}
          transition={active && !reduce ? { repeat: Infinity, duration: 2.2, ease: 'easeInOut' } : {}}
        />
      </div>
      <div className={cn('font-display text-sm font-bold', active ? 'text-beige' : done ? 'text-greige' : 'text-muted')}>
        {phase.label}
      </div>
      <p className={cn('mt-2 min-h-[54px] text-[11px] leading-relaxed', active || done ? 'text-greige' : 'text-muted/80')}>
        {phase.summary}
      </p>
      <div className="mt-3 flex flex-wrap gap-1">
        {phase.agents.map(agent => (
          <span
            key={agent}
            className={cn(
              'rounded-pill border px-1.5 py-0.5 font-mono text-[10px] tracking-tight',
              active ? 'border-hanwha/25 text-hanwha-3' : done ? 'border-line text-greige' : 'border-line text-muted/80',
            )}
          >
            {agent}
          </span>
        ))}
      </div>
    </motion.article>
  )
}

function CommitteeMinutes({ radar }: { radar: RadarResponse }) {
  const minutes = radar.committee_minutes?.length ? radar.committee_minutes : buildResultMinutes(radar)
  const source = radar.market_regime?.source ?? radar.macro_flow?.source ?? radar.data_quality?.regime_source
  return (
    <Card
      eyebrow="Committee Minutes"
      title="회의 결과 메모"
      action={<Badge tone={String(source).includes('mimo') ? 'hanwha' : 'neutral'}>{String(source).includes('mimo') ? 'AI' : 'Result based'}</Badge>}
    >
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        {minutes.map((m, idx) => (
          <article key={`${m.agent}-${idx}`} className="rounded-card border border-line bg-card-2/35 p-4">
            <div className="mb-2 flex items-center gap-2">
              <span className="grid h-7 w-7 place-items-center rounded-pill bg-hanwha/12 text-hanwha">{minuteIcon(m.stage)}</span>
              <div>
                <p className="font-display text-sm font-bold text-beige">{m.agent}</p>
                <p className="font-mono text-[10px] uppercase tracking-[0.08em] text-muted">{m.stage ?? 'committee'}</p>
              </div>
              {m.source && <Badge tone={m.source.includes('mimo') ? 'hanwha' : 'neutral'}>{displaySource(m.source)}</Badge>}
            </div>
            <p className="text-sm leading-relaxed text-greige">{m.text}</p>
          </article>
        ))}
      </div>
    </Card>
  )
}

function buildResultMinutes(radar: RadarResponse) {
  const candidates = radar.stock_candidates ?? radar.top_picks ?? []
  const sectors = radar.sector_flow ?? []
  return [
    { agent: 'Macro PM', stage: 'macro', text: radar.macro_flow?.summary ?? radar.market_regime?.summary ?? '매크로 국면 결과가 정리되었습니다.', source: radar.macro_flow?.source ?? radar.market_regime?.source },
    { agent: 'Sector Analyst', stage: 'sector', text: sectors[0] ? `${sectors[0].sector ?? sectors[0].theme} 레인이 우선 검토 대상으로 올라왔습니다. ${sectors[0].why ?? ''}` : '섹터 레인을 점검했습니다.', source: 'radar' },
    { agent: 'Stock Picker', stage: 'stock', text: candidates[0] ? `${candidates[0].name}(${candidates[0].symbol})를 최상위 후보로 상정했습니다. ${candidates[0].why_now ?? candidates[0].thesis ?? ''}` : '종목 후보를 압축했습니다.', source: candidates[0]?.evidence_source ?? 'radar' },
    { agent: 'PM Chair', stage: 'decision', text: radar.pipeline?.summary ?? `후보 ${candidates.length}개를 회의 결과로 정리했습니다.`, source: radar.market_regime?.source },
  ]
}

function minuteIcon(stage?: string) {
  if (stage === 'macro') return <Activity size={14} />
  if (stage === 'sector') return <GitBranch size={14} />
  if (stage === 'stock') return <Target size={14} />
  return <Gavel size={14} />
}

function displaySource(source: string) {
  return source.includes('mimo') ? 'AI' : source
}

function PipelineOverview({ radar }: { radar: RadarResponse }) {
  const macro = radar.macro_flow ?? {
    label: radar.market_regime?.label,
    summary: radar.market_regime?.summary,
    keywords: radar.market_regime?.news_keywords,
    signals: radar.market_regime?.macro_points,
    source: radar.market_regime?.source,
  }
  const sectors = radar.sector_flow ?? []
  const candidates = radar.stock_candidates ?? radar.top_picks ?? []
  return (
    <Card eyebrow="Committee Decision" title="회의 결론: Macro → Sector → Stock" action={<Badge tone="neutral">{radar.generated_at?.slice(0, 16)}</Badge>}>
      <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        <Stat label="Macro regime" value={macro.label ?? 'neutral'} hint={macro.source} />
        <Stat label="Sector lanes" value={sectors.length || '-'} hint="뉴스/테마 경로" />
        <Stat label="Stock candidates" value={candidates.length || '-'} hint="Top picks" />
      </div>
      <div className="grid gap-3 lg:grid-cols-[1.2fr_1fr_1fr]">
        <FlowStage icon={<Activity size={16} />} title="1. Macro" subtitle={macro.summary} chips={macro.keywords ?? []} />
        <FlowStage icon={<GitBranch size={16} />} title="2. Sector" subtitle="매크로 키워드와 업종 상대강도를 연결" chips={sectors.slice(0, 5).map(s => s.sector ?? s.theme ?? '')} />
        <FlowStage icon={<Target size={16} />} title="3. Stock" subtitle="뉴스 점수·수급·타이밍으로 후보 압축" chips={candidates.slice(0, 5).map(s => s.name)} />
      </div>
      {radar.pipeline?.summary && <p className="mt-4 rounded-chip border border-hanwha/20 bg-hanwha/[0.05] px-3 py-2 text-sm text-greige">{radar.pipeline.summary}</p>}
    </Card>
  )
}

function FlowStage({ icon, title, subtitle, chips }: { icon: ReactNode; title: string; subtitle?: string; chips: string[] }) {
  return (
    <div className="rounded-card border border-line bg-card-2/35 p-4">
      <div className="mb-2 flex items-center gap-2 text-hanwha">{icon}<b className="font-display text-sm text-beige">{title}</b></div>
      <p className="min-h-[42px] text-xs leading-relaxed text-muted">{subtitle}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{chips.filter(Boolean).slice(0, 7).map(chip => <Badge key={chip} tone="neutral">{chip}</Badge>)}</div>
    </div>
  )
}

function SectorFlowBoard({ sectors }: { sectors: SectorFlow[] }) {
  if (!sectors.length) return null
  return (
    <Card eyebrow="Sector Routing" title="뉴스가 연결한 섹터 레인" action={<Badge tone="hanwha">{sectors.length} lanes</Badge>}>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2 xl:grid-cols-3">
        {sectors.slice(0, 6).map((s, i) => (
          <article key={`${s.sector}-${s.theme}`} className="rounded-card border border-line bg-card-2/35 p-4">
            <div className="mb-3 flex items-start justify-between gap-3">
              <div>
                <p className="font-mono text-[11px] text-muted">#{i + 1} {s.sector}</p>
                <h3 className="mt-0.5 font-display text-base font-bold text-beige">{s.theme}</h3>
              </div>
              <Badge tone={s.foreign_flow === 'sell' ? 'down' : s.foreign_flow === 'buy' ? 'up' : 'neutral'}>{s.score ?? '-'}점</Badge>
            </div>
            <p className="mb-3 text-xs leading-relaxed text-greige">{s.why}</p>
            <div className="mb-3 grid grid-cols-2 gap-2">
              <MiniMetric label="뉴스" value={s.news_score ?? '-'} />
              <MiniMetric label="등락" value={typeof s.change === 'number' ? `${s.change > 0 ? '+' : ''}${s.change}%` : '-'} />
            </div>
            <div className="flex flex-wrap gap-1.5">{(s.macro_tags ?? []).map(tag => <Badge key={tag} tone="neutral">{tag}</Badge>)}</div>
          </article>
        ))}
      </div>
    </Card>
  )
}

function CandidateBoard({ candidates, selectedSymbol, onSelect }: { candidates: Array<StockCandidate | RadarPick>; selectedSymbol?: string; onSelect: (pick: StockCandidate | RadarPick) => void }) {
  if (!candidates.length) return <EmptyState icon={<Target size={20} />} title="후보 없음" description="다른 뉴스/테마 키워드로 다시 회의를 열어 보세요." />
  return (
    <Card eyebrow="Stock Candidates" title="투자 아이디어 후보" action={<Badge tone="hanwha" dot>행 클릭 → 회의록 열기</Badge>} noPadding>
      <div className="divide-y divide-line/60">
        {candidates.map((p, i) => (
          <CandidateRow key={`${p.symbol}-${i}`} pick={p} rank={i + 1} selected={p.symbol === selectedSymbol} onSelect={() => onSelect(p)} />
        ))}
      </div>
    </Card>
  )
}

function CandidateRow({ pick, rank, selected, onSelect }: { pick: StockCandidate | RadarPick; rank: number; selected: boolean; onSelect: () => void }) {
  const timing = pick.timing_signal?.signal ?? 'enter'
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        'grid w-full grid-cols-1 gap-4 px-5 py-4 text-left transition-colors hover:bg-hanwha/[0.04] xl:grid-cols-[54px_1.2fr_1fr_118px] xl:items-start',
        selected && 'bg-hanwha/[0.07] ring-1 ring-inset ring-hanwha/35',
      )}
    >
      <div className="flex items-center gap-3 xl:block">
        <div className="grid h-10 w-10 place-items-center rounded-pill border border-hanwha/30 bg-hanwha/10 font-mono font-bold text-hanwha">{rank}</div>
        <Badge tone={flowTone(timing)}>{timing.toUpperCase()}</Badge>
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <h3 className="font-display text-lg font-bold text-beige">{pick.name}</h3>
          <span className="font-mono text-xs text-muted">{pick.symbol}</span>
          <Badge tone="neutral">{pick.sector}</Badge>
          <Badge tone="blue">Score {pick.score}</Badge>
        </div>
        <p className="mt-1 text-sm leading-relaxed text-greige">{pick.thesis}</p>
        <p className="mt-2 text-xs leading-relaxed text-muted">{pick.why_now}</p>
        <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
          {(pick.route ?? [pick.sector, pick.theme, pick.name]).filter(Boolean).map((step, idx, arr) => (
            <span key={`${step}-${idx}`} className="inline-flex items-center gap-1">
              <span className="rounded-pill border border-line bg-card-2 px-2 py-0.5">{step}</span>
              {idx < arr.length - 1 && <ArrowDownToDot size={11} className="rotate-[-90deg] text-hanwha" />}
            </span>
          ))}
        </div>
      </div>
      <div>
        <FactorBars scores={pick.factor_scores ?? {}} />
        {pick.timing_signal?.reason && <p className="mt-2 rounded-chip bg-card-2/50 px-3 py-1.5 text-[11px] text-muted">{pick.timing_signal.reason}</p>}
      </div>
      <div className="flex items-center justify-start xl:justify-end">
        <Badge tone={selected ? 'hanwha' : 'neutral'}>{selected ? '회의록 표시 중' : '회의록 열기'}</Badge>
      </div>
    </button>
  )
}

function CandidateDecisionReport({ pick, radar }: { pick: StockCandidate | RadarPick | null; radar: RadarResponse }) {
  if (!pick) {
    return <EmptyState icon={<MessagesSquare size={20} />} title="후보를 클릭하세요" description="후보 행을 클릭하면 서브에이전트 회의 결과가 이곳에 카드 형태로 펼쳐집니다." />
  }
  const sector = (radar.sector_flow ?? []).find(s => s.sector === pick.sector || s.theme === pick.theme)
  const evidence = (pick.evidence ?? []).slice(0, 3)
  const checklist = 'checklist' in pick ? pick.checklist ?? [] : []
  const counterEvidence = 'counter_evidence' in pick ? pick.counter_evidence ?? [] : []
  return (
    <Card
      eyebrow="Decision Minutes"
      title={`${pick.name} 회의 결과`}
      action={<Badge tone={flowTone(pick.timing_signal?.signal)}>{pick.timing_signal?.signal?.toUpperCase() ?? 'ENTER'}</Badge>}
    >
      <div className="relative overflow-hidden rounded-[28px] border border-hanwha/25 bg-gradient-to-br from-hanwha/[0.18] via-card-2/45 to-canvas p-5">
        <div className="absolute -right-16 -top-16 h-48 w-48 rounded-full bg-hanwha/10 blur-3xl" />
        <div className="relative grid grid-cols-1 gap-5 xl:grid-cols-[1.1fr_0.9fr]">
          <div>
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge tone="hanwha">PM 의장 채택</Badge>
              <Badge tone="neutral">LLM · AI</Badge>
              <Badge tone="neutral">{pick.symbol}</Badge>
              <Badge tone="blue">Score {pick.score}</Badge>
              <Badge tone="neutral">{pick.sector}</Badge>
            </div>
            <h3 className="font-display text-2xl font-black text-beige">{pick.theme}</h3>
            <p className="mt-3 text-sm leading-relaxed text-greige">{pick.thesis || pick.why_now || '회의 결과 요약을 생성했습니다.'}</p>
            {pick.why_now && <p className="mt-3 rounded-card border border-line bg-canvas/35 p-3 text-xs leading-relaxed text-muted"><b className="text-hanwha">Why now</b> · {pick.why_now}</p>}
            <div className="mt-4 flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
              {(pick.route ?? [radar.macro_flow?.label, pick.sector, pick.theme, pick.name]).filter(Boolean).map((step, idx, arr) => (
                <span key={`${step}-${idx}`} className="inline-flex items-center gap-1">
                  <span className="rounded-pill border border-hanwha/25 bg-hanwha/[0.06] px-2.5 py-1 text-greige">{step}</span>
                  {idx < arr.length - 1 && <ArrowDownToDot size={11} className="rotate-[-90deg] text-hanwha" />}
                </span>
              ))}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <MiniMetric label="Discovery" value={pick.discovery_score ?? pick.score} />
            <MiniMetric label="Conviction" value={pick.conviction_score ?? pick.score} />
            <MiniMetric label="Sector score" value={sector?.score ?? '-'} />
            <MiniMetric label="News score" value={sector?.news_score ?? '-'} />
          </div>
        </div>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-3">
        <AgentMinute title="Macro PM" body={radar.macro_flow?.summary ?? radar.market_regime?.summary ?? '매크로 국면을 확인했습니다.'} tags={radar.macro_flow?.keywords ?? radar.market_regime?.news_keywords ?? []} />
        <AgentMinute title="Sector Analyst" body={sector?.why ?? `${pick.sector} 레인을 후보 경로로 채택했습니다.`} tags={sector?.macro_tags ?? [pick.sector, pick.theme]} />
        <AgentMinute title="Risk Reviewer" body={pick.timing_signal?.reason ?? counterEvidence[0] ?? '추격 매수 리스크와 타이밍을 별도 점검합니다.'} tags={counterEvidence.slice(0, 2)} tone="down" />
      </div>

      {(evidence.length > 0 || checklist.length > 0) && (
        <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {evidence.length > 0 && <ListBox title="회의 근거" items={evidence.map(evidenceLabel)} />}
          {checklist.length > 0 && <ListBox title="추가 확인 액션" items={checklist} />}
        </div>
      )}
    </Card>
  )
}

function evidenceLabel(item: NonNullable<StockCandidate['evidence']>[number]) {
  if ('detail' in item && item.detail) return item.detail
  if ('claim' in item && item.claim) return item.claim
  return item.title ?? '근거 확인'
}

function AgentMinute({ title, body, tags, tone = 'up' }: { title: string; body: string; tags: string[]; tone?: 'up' | 'down' }) {
  return (
    <div className={cn('rounded-card border p-4', tone === 'down' ? 'border-down/20 bg-down/[0.04]' : 'border-line bg-card-2/35')}>
      <p className={cn('mb-2 font-mono text-[11px] font-bold uppercase tracking-[0.06em]', tone === 'down' ? 'text-down' : 'text-hanwha')}>{title}</p>
      <p className="min-h-[58px] text-xs leading-relaxed text-greige">{body}</p>
      <div className="mt-3 flex flex-wrap gap-1.5">{tags.filter(Boolean).slice(0, 4).map(tag => <Badge key={tag} tone={tone === 'down' ? 'down' : 'neutral'}>{tag}</Badge>)}</div>
    </div>
  )
}
function FactorBars({ scores }: { scores: FactorScores }) {
  const entries = Object.entries(scores)
  if (!entries.length) return null
  return (
    <div className="space-y-1.5">
      {entries.map(([k, v]) => (
        <div key={k} className="grid grid-cols-[70px_1fr_34px] items-center gap-2 text-[11px]">
          <span className="text-muted">{FACTOR_LABEL[k] ?? k}</span>
          <span className="h-1.5 overflow-hidden rounded-full bg-card-2"><span className="block h-full rounded-full bg-hanwha" style={{ width: `${Math.max(0, Math.min(100, v))}%` }} /></span>
          <span className="font-mono text-greige">{v}</span>
        </div>
      ))}
    </div>
  )
}

function NewsTape({ news }: { news: NewsFlowItem[] }) {
  if (!news.length) return null
  return (
    <Card eyebrow="Evidence Tape" title="후보를 만든 뉴스 흐름" action={<Badge tone="neutral">{news.length} items</Badge>}>
      <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
        {news.slice(0, 8).map((n, i) => (
          <div key={`${n.title}-${i}`} className="rounded-chip border border-line bg-card-2/35 px-3 py-2">
            <div className="mb-1 flex items-center gap-2 font-mono text-[10px] text-muted"><Newspaper size={12} />{n.source ?? 'news'}{n.published_at && <span>· {String(n.published_at).slice(0, 10)}</span>}</div>
            <p className="text-sm leading-relaxed text-greige">{n.title}</p>
          </div>
        ))}
      </div>
    </Card>
  )
}

function MiniMetric({ label, value }: { label: string; value: ReactNode }) {
  return <div className="rounded-[10px] border border-line bg-canvas/35 px-3 py-2"><p className="font-mono text-[10px] text-muted">{label}</p><p className="mt-0.5 font-mono text-sm font-bold text-beige">{value}</p></div>
}

function ListBox({ title, items, tone = 'up' }: { title: string; items: string[]; tone?: 'up' | 'down' }) {
  return <div className={cn('rounded-card border p-3', tone === 'up' ? 'border-up/20 bg-up/[0.04]' : 'border-down/20 bg-down/[0.04]')}><p className={cn('mb-2 text-xs font-semibold', tone === 'up' ? 'text-up' : 'text-down')}>{title}</p><ul className="space-y-1 text-xs text-greige">{items.map(x => <li key={x} className="flex gap-1"><CheckCircle2 size={12} className="mt-0.5 shrink-0" />{x}</li>)}</ul></div>
}

export default IdeaLab





