import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import {
  ArrowDownRight,
  ArrowUpRight,
  Briefcase,
  CheckCircle2,
  Clock,
  Gavel,
  HeartPulse,
  Landmark,
  LineChart as LineChartIcon,
  MessagesSquare,
  MinusCircle,
  Newspaper,
  Search,
  ShieldAlert,
  Users,
} from 'lucide-react'
import { Markdown } from './Markdown'
import { Badge, Card, EmptyState, ErrorState, SectionHeader, Spinner } from './ui'
import { cn } from '../lib/utils'
import { LiveFeed, type AgentMessage } from './committee/LiveFeed'

const REPORT_TABS: ReadonlyArray<{ id: string; label: string; icon: ReactNode }> = [
  { id: 'final_trade_decision', label: '최종결정', icon: <Gavel size={13} /> },
  { id: 'investment_plan', label: '투자계획', icon: <Users size={13} /> },
  { id: 'investment_debate', label: '투자토론', icon: <MessagesSquare size={13} /> },
  { id: 'risk_debate', label: '리스크토론', icon: <ShieldAlert size={13} /> },
  { id: 'market_report', label: '기술·시장', icon: <LineChartIcon size={13} /> },
  { id: 'fundamentals_report', label: '펀더멘털', icon: <Landmark size={13} /> },
  { id: 'news_report', label: '뉴스', icon: <Newspaper size={13} /> },
  { id: 'sentiment_report', label: '심리', icon: <HeartPulse size={13} /> },
  { id: 'trader_investment_plan', label: '트레이딩', icon: <Briefcase size={13} /> },
]

const PIPELINE: ReadonlyArray<{ key: string; label: string; icon: ReactNode; agents: string[]; image: string }> = [
  { key: 'analysts', label: '애널리스트 조사', icon: <Search size={15} />, agents: ['기술', '펀더멘털', '뉴스', '심리'], image: '/illustrations/process/committee-research-agent.png' },
  { key: 'debate', label: 'Bull / Bear 토론', icon: <MessagesSquare size={15} />, agents: ['Bull 리서처', 'Bear 리서처', '리서치 매니저'], image: '/illustrations/process/committee-debate-agent.png' },
  { key: 'risk', label: '리스크 심의', icon: <ShieldAlert size={15} />, agents: ['공격', '중립', '보수', '리스크 매니저'], image: '/illustrations/process/committee-risk-agent.png' },
  { key: 'decision', label: '트레이딩·최종결정', icon: <Gavel size={15} />, agents: ['트레이더', '포트폴리오 매니저', '의장'], image: '/illustrations/process/committee-decision-agent.png' },
]

type Result = { ticker: string; input: string; is_kr: boolean; decision: string; reports: Record<string, string>; transcript?: AgentMessage[] }
type Stage = 'idle' | 'running' | 'done' | 'error'

const STAGE_TO_PHASE: Record<string, number> = { starting: 0, analysts: 0, research_debate: 1, risk_debate: 2, decision: 3, done: 3 }

const inputBase = 'w-full rounded-chip border border-line bg-canvas px-3.5 py-2.5 text-sm text-beige placeholder:text-muted/70 transition-colors focus:border-hanwha focus:outline-none focus:ring-1 focus:ring-hanwha/40'

function FieldLabel({ children }: { children: ReactNode }) {
  return <span className="mb-1.5 block font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">{children}</span>
}

type Verdict = 'buy' | 'sell' | 'hold'
function classifyDecision(decision?: string): Verdict {
  const d = (decision ?? '').toUpperCase()
  if (d.includes('BUY') || d.includes('매수')) return 'buy'
  if (d.includes('SELL') || d.includes('매도')) return 'sell'
  return 'hold'
}

const VERDICT_META: Record<Verdict, { label: string; tone: 'up' | 'down' | 'neutral'; icon: ReactNode; text: string; ring: string; surface: string }> = {
  buy: { label: 'BUY · 매수', tone: 'up', icon: <ArrowUpRight size={22} />, text: 'text-up', ring: 'border-up/30', surface: 'bg-up/[0.07]' },
  sell: { label: 'SELL · 매도', tone: 'down', icon: <ArrowDownRight size={22} />, text: 'text-down', ring: 'border-down/30', surface: 'bg-down/[0.07]' },
  hold: { label: 'HOLD · 관망', tone: 'neutral', icon: <MinusCircle size={22} />, text: 'text-greige', ring: 'border-line', surface: 'bg-card-2/40' },
}

export function AICommittee({ apiBase, presetTicker }: { apiBase: string; presetTicker?: string }) {
  const [ticker, setTicker] = useState('삼성전자')
  const [stage, setStage] = useState<Stage>('idle')
  const [stageMsg, setStageMsg] = useState('')
  const [stderrMsg, setStderrMsg] = useState('')
  const [activePhase, setActivePhase] = useState(0)
  const [result, setResult] = useState<Result | null>(null)
  const [activeReport, setActiveReport] = useState('final_trade_decision')
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [jobId, setJobId] = useState<string | null>(null)
  const [autoLoadFailed, setAutoLoadFailed] = useState(false)
  const pollRef = useRef<number | null>(null)
  const msgPollRef = useRef<number | null>(null)
  const msgSinceRef = useRef(0)
  const feedBottomRef = useRef<HTMLDivElement | null>(null)
  const runRef = useRef<(override?: string) => void>(() => {})
  const lastPresetRef = useRef<string | null>(null)
  const autoloadedRef = useRef(false)

  const stopTimers = useCallback(() => {
    if (pollRef.current) window.clearInterval(pollRef.current)
    if (msgPollRef.current) window.clearInterval(msgPollRef.current)
    pollRef.current = null
    msgPollRef.current = null
  }, [])

  useEffect(() => () => stopTimers(), [stopTimers])

  // 마운트 시 최근 위원회 결과 자동 로드(데모 지속성). 사용자가 소집을 시작하면 건너뛰고, 실패 시 안내 플래그를 세운다.
  useEffect(() => {
    if (typeof fetch !== 'function') return
    let cancelled = false
    fetch(`${apiBase}/api/committee/latest`)
      .then(x => x.json())
      .then((d) => {
        if (cancelled || autoloadedRef.current) return
        if (d && d.reports && Object.keys(d.reports).length) {
          autoloadedRef.current = true
          setResult(d as Result)
          setActiveReport(d.reports.final_trade_decision ? 'final_trade_decision' : (REPORT_TABS.find(t => d.reports[t.id])?.id ?? 'final_trade_decision'))
          setStage('done')
        } else {
          if (!cancelled) setAutoLoadFailed(true)
        }
      })
      .catch(() => { if (!cancelled) setAutoLoadFailed(true) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiBase])

  const loadLatest = useCallback(async () => {
    autoloadedRef.current = true
    stopTimers()
    setStage('idle')
    setResult(null)
    setMessages([])
    setStderrMsg('')
    try {
      const d = await fetch(`${apiBase}/api/committee/latest`).then(x => x.json())
      if (d && d.reports && Object.keys(d.reports).length) {
        setResult(d as Result)
        setActiveReport(d.reports.final_trade_decision ? 'final_trade_decision' : (REPORT_TABS.find(t => d.reports[t.id])?.id ?? 'final_trade_decision'))
        setStage('done')
      } else {
        setStageMsg('저장된 최근 심의 결과가 없습니다. [위원회 소집]으로 새로 실행하세요.')
        setStage('error')
      }
    } catch {
      setStageMsg('최근 결과 로드 실패')
      setStage('error')
    }
  }, [apiBase, stopTimers])

  const run = async (override?: string) => {
    const target = (typeof override === 'string' ? override : ticker).trim()
    if (!target) return
    autoloadedRef.current = true
    stopTimers()
    setStage('running')
    setResult(null)
    setMessages([])
    setJobId(null)
    msgSinceRef.current = 0
    setActivePhase(0)
    setStageMsg('위원회 소집 중...')
    setStderrMsg('')

    try {
      const r = await fetch(`${apiBase}/api/committee/run?ticker=${encodeURIComponent(target)}`, { method: 'POST' })
      const { job_id } = await r.json()
      if (!job_id) throw new Error('작업 ID를 받지 못했습니다.')
      setJobId(job_id)

      msgPollRef.current = window.setInterval(async () => {
        try {
          const md = await fetch(`${apiBase}/api/committee/messages/${job_id}?since=${msgSinceRef.current}`).then(x => x.json())
          if (md.messages?.length) {
            setMessages(prev => [...prev, ...md.messages])
            const last = md.messages[md.messages.length - 1]
            msgSinceRef.current = last.idx + 1
            // 진행 단계를 마지막 발언 stage로 즉시 동기화 — 라이브피드와 4단계 진행카드의 desync 제거
            if (typeof last.stage === 'string' && last.stage in STAGE_TO_PHASE) {
              setActivePhase(STAGE_TO_PHASE[last.stage])
            }
            setTimeout(() => feedBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
          }
        } catch {}
      }, 2000)

      pollRef.current = window.setInterval(async () => {
        try {
          const s = await fetch(`${apiBase}/api/committee/status?job_id=${job_id}`).then(x => x.json())
          if (typeof s.stage === 'string' && s.stage in STAGE_TO_PHASE) setActivePhase(STAGE_TO_PHASE[s.stage])
          setStageMsg(`${s.stage_label ?? s.stage ?? '진행 중'}${s.ticker ? ' · ' + s.ticker : ''}`)
          if (s.stage === 'done') {
            stopTimers()
            const res: Result = await fetch(`${apiBase}/api/committee/result?job_id=${job_id}`).then(x => x.json())
            setResult(res)
            const firstAvail = REPORT_TABS.find(t => res.reports?.[t.id])?.id ?? 'final_trade_decision'
            setActiveReport(res.reports?.final_trade_decision ? 'final_trade_decision' : firstAvail)
            setStage('done')
          } else if (s.stage === 'error' || s.stage === 'unknown') {
            stopTimers()
            setStageMsg(s.error ?? s.stage_label ?? '위원회 실행 중 오류가 발생했습니다.')
            setStderrMsg(s.stderr ?? s.trace ?? '')
            setStage('error')
          }
        } catch (e) {
          stopTimers()
          setStageMsg(e instanceof Error ? e.message : '상태 조회 실패')
          setStage('error')
        }
      }, 5000)
    } catch (e) {
      stopTimers()
      setStageMsg(e instanceof Error ? e.message : '위원회 소집 실패')
      setStage('error')
    }
  }

  useEffect(() => { runRef.current = run })
  useEffect(() => {
    const t = (presetTicker ?? '').trim()
    if (!t || t === lastPresetRef.current) return
    lastPresetRef.current = t
    setTicker(t)
    runRef.current(t)
  }, [presetTicker])

  const verdict = classifyDecision(result?.decision)
  const vMeta = VERDICT_META[verdict]
  const availableTabs = REPORT_TABS.filter(t => result?.reports?.[t.id])

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="space-y-7">
      <SectionHeader
        eyebrow="AI Committee"
        title="AI 투자위원회"
        description="14개 AI 에이전트가 분석·토론·리스크 심의를 거쳐 투자 의견을 도출합니다."
        action={<Badge tone="hanwha" dot>TradingAgents</Badge>}
      />

      <Card eyebrow="Convene" title="위원회 소집">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <label className="flex-1">
            <FieldLabel>종목</FieldLabel>
            <input value={ticker} onChange={e => setTicker(e.target.value)} onKeyDown={e => e.key === 'Enter' && stage !== 'running' && run()} className={inputBase} placeholder="종목 입력 (삼성전자 / 005930 / NVDA)" disabled={stage === 'running'} />
          </label>
          <div className="flex gap-2">
            <motion.button onClick={() => run()} disabled={stage === 'running' || !ticker.trim()} className={cn('inline-flex items-center justify-center gap-2 rounded-chip bg-hanwha px-5 py-2.5 text-sm font-semibold text-canvas shadow-glow transition-all hover:bg-hanwha-2 disabled:cursor-not-allowed disabled:opacity-50 disabled:shadow-none')}>
              {stage === 'running' ? <Spinner size={15} className="text-canvas" /> : <Gavel size={15} />}
              {stage === 'running' ? '심의 중' : '위원회 소집'}
            </motion.button>
            <button type="button" onClick={loadLatest} disabled={stage === 'running'} className={cn('inline-flex items-center justify-center gap-2 rounded-chip border border-hanwha/35 bg-hanwha/[0.06] px-4 py-2.5 text-sm font-semibold text-greige transition-all hover:border-hanwha/55 hover:text-beige disabled:cursor-not-allowed disabled:opacity-50')}>
              <Clock size={14} />
              최근 결과
              <span className="font-mono text-[10px] text-muted">즉시 보기</span>
            </button>
          </div>
        </div>
        {autoLoadFailed && stage === 'idle' && (
          <p className="mt-3 text-xs text-muted">
            이전 회의 결과가 없습니다. <span className="text-hanwha">[위원회 소집]</span>을 눌러 바로 실행해 보세요.
          </p>
        )}
        {!autoLoadFailed && (
          <p className="mt-3 text-xs text-muted">분석가 · Bull/Bear 토론 · 리스크 매니저 등 14개 에이전트가 멀티라운드로 심의합니다.</p>
        )}
      </Card>

      <Card eyebrow={stage === 'running' ? 'In Session' : 'Committee Workflow'} title="위원회 심의 진행" action={<Badge tone={stage === 'running' ? 'hanwha' : stage === 'done' ? 'up' : 'neutral'} dot>{stage === 'running' ? <span className="animate-pulse-soft">LIVE</span> : stage === 'done' ? 'Complete' : 'Ready'}</Badge>}>
        <PipelineProgress activePhase={stage === 'idle' ? -1 : activePhase} />
        {stage === 'running' && (
          <>
            <div className="mt-4 flex items-center gap-2 rounded-chip border border-line bg-canvas/50 px-3 py-2 font-mono text-[11px] text-muted"><Spinner size={13} /><span className="truncate">상태 · {stageMsg || '진행 중'}</span></div>
            <LiveFeed messages={messages} feedBottomRef={feedBottomRef} emptyLabel="에이전트 소집 중 — 첫 발언을 기다리는 중입니다…" />
          </>
        )}
      </Card>

      {stage === 'error' && <ErrorState title="위원회 실행 실패" message={stageMsg || '위원회 심의 중 문제가 발생했습니다.'} onRetry={() => run()} />}
      {stderrMsg && (
        import.meta.env.DEV
          ? <details className="mt-2 rounded-card border border-line bg-canvas/60 p-3 text-xs text-greige"><summary className="cursor-pointer font-mono text-[11px] text-muted">개발용 오류 상세</summary><pre className="mt-2 max-h-48 overflow-auto">{stderrMsg}</pre></details>
          : null
      )}

      {stage === 'done' && result && (
        <div className="space-y-6">
          <div className={cn('flex flex-col gap-4 rounded-card border p-5 shadow-card sm:flex-row sm:items-center sm:justify-between', vMeta.ring, vMeta.surface)}>
            <div className="flex items-center gap-4"><div className={cn('grid h-12 w-12 place-items-center rounded-pill', vMeta.surface, vMeta.text)}>{vMeta.icon}</div><div><div className="font-display text-lg font-bold text-beige">{result.input}</div><div className="font-mono text-sm text-muted">{result.ticker}</div></div></div>
            <div className={cn('flex items-center gap-2 font-display text-2xl font-bold', vMeta.text)}><CheckCircle2 size={20} />{vMeta.label}</div>
          </div>
          {result.decision && <div className="rounded-card border border-line bg-card-2/30 px-4 py-3"><div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">Decision Raw</div><p className="font-mono text-sm leading-relaxed text-greige">{result.decision}</p></div>}
          {(messages.length > 0 || (result.transcript?.length ?? 0) > 0) && (
            <Card eyebrow="Committee Minutes" title="위원회 토론 발언" action={<Badge tone="neutral" dot>{messages.length || result.transcript?.length || 0}건</Badge>}>
              <LiveFeed messages={messages.length ? messages : (result.transcript ?? [])} feedBottomRef={feedBottomRef} emptyLabel="발언 기록이 없습니다." />
            </Card>
          )}
          <Card eyebrow="Committee Reports" title="심의 리포트" noPadding>
            {availableTabs.length === 0 ? <div className="px-5 pb-5"><EmptyState icon={<MessagesSquare size={20} />} title="리포트가 없습니다" description="이번 심의에서 생성된 세부 리포트가 없습니다." /></div> : <><div className="relative flex gap-1 overflow-x-auto border-b border-line px-3">{availableTabs.map(t => <button key={t.id} onClick={() => setActiveReport(t.id)} className={cn('relative inline-flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-xs font-semibold transition-colors', activeReport === t.id ? 'text-hanwha' : 'text-muted hover:text-beige')}>{t.icon}{t.label}{activeReport === t.id && <motion.span layoutId="committeeReportTab" className="absolute inset-x-2 -bottom-px h-0.5 rounded-pill bg-hanwha" />}</button>)}</div><div className="px-5 py-5">{result.reports?.[activeReport] ? <Markdown>{result.reports[activeReport]}</Markdown> : <EmptyState title="해당 리포트 없음" description="선택한 항목의 리포트가 비어 있습니다." />}</div></>}
          </Card>
        </div>
      )}
    </motion.div>
  )
}

function PipelineProgress({ activePhase }: { activePhase: number }) {
  const reduce = useReducedMotion()
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {PIPELINE.map((phase, idx) => {
        const isDone = idx < activePhase
        const isActive = idx === activePhase
        return (
          <motion.div
            key={phase.key}
            animate={isActive && !reduce ? { y: [0, -3, 0] } : { y: 0 }}
            transition={isActive && !reduce ? { repeat: Infinity, duration: 2.2, ease: 'easeInOut' } : {}}
            className={cn(
              'relative overflow-hidden rounded-card border p-4 transition-colors',
              isActive ? 'border-hanwha/55 bg-hanwha/[0.06] shadow-glow' : isDone ? 'border-hanwha/30 bg-card-2/40' : 'border-line bg-canvas/40',
            )}
          >
            {isActive && (
              <motion.span
                className="absolute inset-x-0 top-0 h-0.5 bg-hanwha"
                animate={reduce ? { scaleX: 1, originX: 0 } : { scaleX: [0, 1, 0], originX: [0, 0, 1] }}
                transition={reduce ? {} : { duration: 2.2, ease: 'easeInOut', repeat: Infinity }}
              />
            )}
            <div className="mb-2.5 flex items-center justify-between">
              <span className={cn('grid h-8 w-8 place-items-center rounded-pill', isActive ? 'bg-hanwha/15 text-hanwha' : isDone ? 'bg-up/12 text-up' : 'bg-card-2 text-muted')}>
                {isDone ? <CheckCircle2 size={15} /> : isActive ? <Spinner size={15} /> : phase.icon}
              </span>
              <span className="font-mono text-[11px] font-semibold tabular-nums text-muted">{String(idx + 1).padStart(2, '0')}/04</span>
            </div>
            <div className="relative mb-3 grid h-40 place-items-center overflow-hidden rounded-card bg-card/30 px-1 pb-4 pt-2">
              <motion.img
                src={phase.image}
                alt=""
                aria-hidden="true"
                loading="lazy"
                decoding="async"
                className={cn(
                  'h-[150px] w-full object-contain object-center transition-opacity',
                  !isDone && !isActive && 'opacity-35 grayscale',
                )}
                animate={isActive && !reduce ? { scale: [1, 1.045, 1] } : { scale: 1 }}
                transition={isActive && !reduce ? { repeat: Infinity, duration: 2.2, ease: 'easeInOut' } : {}}
              />
            </div>
            <div className={cn('font-display text-sm font-bold', isActive ? 'text-beige' : isDone ? 'text-greige' : 'text-muted')}>{phase.label}</div>
            <div className="mt-2 flex flex-wrap gap-1">
              {phase.agents.map(a => <span key={a} className={cn('rounded-pill border px-1.5 py-0.5 font-mono text-[10px]', isActive ? 'border-hanwha/25 text-hanwha-3' : isDone ? 'border-line text-greige' : 'border-line text-muted/80')}>{a}</span>)}
            </div>
          </motion.div>
        )
      })}
    </div>
  )
}

export default AICommittee

