/**
 * CommitteeLatestWidget
 * 마운트 시 GET /api/committee/latest → 작은 카드 위젯
 * 클릭 → Modal: 4단계 14에이전트 파이프라인(완료 시각화) + 9개 리포트 탭
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Gavel,
  ArrowUpRight,
  ArrowDownRight,
  MinusCircle,
  CheckCircle2,
  Search,
  MessagesSquare,
  ShieldAlert,
  ChevronRight,
  Building2,
  Landmark,
  LineChart as LineChartIcon,
  Newspaper,
  HeartPulse,
  Briefcase,
  Users,
} from 'lucide-react'
import { Markdown } from '../Markdown'
import { Badge, Card, EmptyState, ErrorState, Modal, Skeleton } from '../ui'
import { cn } from '../../lib/utils'

// ── 타입 ─────────────────────────────────────────────────────────────────────
type CommitteeLatest = {
  ticker?: string | null
  input?: string | null
  decision?: string | null
  reports?: Record<string, string>
  is_seed?: boolean
  available?: boolean
}

type LoadState = 'loading' | 'ready' | 'unavailable' | 'error'

// ── 리포트 탭 ─────────────────────────────────────────────────────────────────
const REPORT_TABS: ReadonlyArray<{ id: string; label: string; icon: ReactNode }> = [
  { id: 'final_trade_decision',   label: '최종결정',   icon: <Gavel size={13} /> },
  { id: 'investment_plan',        label: '투자위원회', icon: <Users size={13} /> },
  { id: 'investment_debate',      label: '투자토론',   icon: <MessagesSquare size={13} /> },
  { id: 'risk_debate',            label: '리스크토론', icon: <ShieldAlert size={13} /> },
  { id: 'market_report',          label: '기술적',     icon: <LineChartIcon size={13} /> },
  { id: 'fundamentals_report',    label: '재무',       icon: <Landmark size={13} /> },
  { id: 'news_report',            label: '뉴스',       icon: <Newspaper size={13} /> },
  { id: 'sentiment_report',       label: '심리',       icon: <HeartPulse size={13} /> },
  { id: 'trader_investment_plan', label: '트레이딩',   icon: <Briefcase size={13} /> },
]

// ── 4단계 파이프라인 ──────────────────────────────────────────────────────────
const PIPELINE: ReadonlyArray<{
  key: string
  label: string
  icon: ReactNode
  agents: string[]
}> = [
  {
    key: 'analysts',
    label: '애널리스트 조사',
    icon: <Search size={14} />,
    agents: ['기술적', '재무', '뉴스', '심리'],
  },
  {
    key: 'debate',
    label: 'Bull / Bear 토론',
    icon: <MessagesSquare size={14} />,
    agents: ['Bull 리서처', 'Bear 리서처', '리서치 매니저'],
  },
  {
    key: 'risk',
    label: '리스크 심의',
    icon: <ShieldAlert size={14} />,
    agents: ['공격적', '중립적', '보수적', '리스크 매니저'],
  },
  {
    key: 'decision',
    label: '트레이딩·최종결정',
    icon: <Gavel size={14} />,
    agents: ['트레이더', '포트폴리오 매니저', '의장'],
  },
]

// ── 최종 결정 분류 (한국 관례) ────────────────────────────────────────────────
type Verdict = 'buy' | 'sell' | 'hold'
function classifyDecision(d?: string | null): Verdict {
  const s = (d ?? '').toUpperCase()
  if (s.includes('BUY') || s.includes('매수')) return 'buy'
  if (s.includes('SELL') || s.includes('매도')) return 'sell'
  return 'hold'
}
const VERDICT_META: Record<
  Verdict,
  { label: string; tone: 'up' | 'down' | 'neutral'; icon: ReactNode; text: string; ring: string; surface: string }
> = {
  buy: {
    label: 'BUY · 매수',
    tone: 'up',
    icon: <ArrowUpRight size={18} strokeWidth={2.4} />,
    text: 'text-up',
    ring: 'border-up/30',
    surface: 'bg-up/[0.07]',
  },
  sell: {
    label: 'SELL · 매도',
    tone: 'down',
    icon: <ArrowDownRight size={18} strokeWidth={2.4} />,
    text: 'text-down',
    ring: 'border-down/30',
    surface: 'bg-down/[0.07]',
  },
  hold: {
    label: 'HOLD · 관망',
    tone: 'neutral',
    icon: <MinusCircle size={18} strokeWidth={2.2} />,
    text: 'text-greige',
    ring: 'border-line',
    surface: 'bg-card-2/40',
  },
}

// ── 파이프라인 완료 시각화 (모달용) ─────────────────────────────────────────
function PipelineCompleted() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {PIPELINE.map((phase, idx) => (
        <div
          key={phase.key}
          className="relative overflow-hidden rounded-card border border-line bg-card-2/40 p-3"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="grid h-7 w-7 place-items-center rounded-pill bg-up/10 text-up">
              <CheckCircle2 size={14} />
            </span>
            <span className="font-mono text-[10px] font-semibold tabular-nums text-muted">
              {String(idx + 1).padStart(2, '0')}/04
            </span>
          </div>
          <div className="font-display text-xs font-bold text-greige">{phase.label}</div>
          <div className="mt-1.5 flex flex-wrap gap-1">
            {phase.agents.map(a => (
              <span
                key={a}
                className="rounded-pill border border-line px-1.5 py-0.5 font-mono text-[10px] text-greige"
              >
                {a}
              </span>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ── 메인 컴포넌트 ────────────────────────────────────────────────────────────
export function CommitteeLatestWidget({ apiBase }: { apiBase: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [data, setData] = useState<CommitteeLatest | null>(null)
  const [modalOpen, setModalOpen] = useState(false)
  const [activeReport, setActiveReport] = useState('final_trade_decision')

  const load = useCallback(() => {
    setState('loading')
    fetch(`${apiBase}/api/committee/latest`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: CommitteeLatest) => {
        setData(d)
        if (d.available === false) {
          setState('unavailable')
        } else {
          setState('ready')
          const firstAvail =
            REPORT_TABS.find(t => d.reports?.[t.id])?.id ?? 'final_trade_decision'
          setActiveReport(
            d.reports?.['final_trade_decision'] ? 'final_trade_decision' : firstAvail,
          )
        }
      })
      .catch(() => setState('error'))
  }, [apiBase])

  useEffect(() => { load() }, [load])

  // ── 로딩 ──
  if (state === 'loading') {
    return <Skeleton className="h-[96px] w-full rounded-card" />
  }

  // ── 에러 ──
  if (state === 'error') {
    return (
      <ErrorState
        title="위원회 결과 조회 실패"
        onRetry={load}
        className="rounded-card border border-line bg-card"
      />
    )
  }

  // ── 미실행 ──
  if (state === 'unavailable' || !data) {
    return (
      <div className="flex flex-col gap-2 rounded-card border border-line bg-card px-4 py-4">
        <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
          <Gavel size={13} />
          최신 AI 위원회
        </div>
        <EmptyState
          icon={<Gavel size={18} strokeWidth={1.75} />}
          title="위원회 미실행"
          description="AI Committee 탭에서 위원회를 소집해 주세요."
          className="border-0 bg-transparent px-0 py-3"
        />
      </div>
    )
  }

  const verdict = classifyDecision(data.decision)
  const meta = VERDICT_META[verdict]
  const displayTicker =
    (data.input ?? data.ticker ?? '').trim() || '대상 종목'
  const availableTabs = REPORT_TABS.filter(t => data.reports?.[t.id])

  return (
    <>
      {/* ── 위젯 카드 (클릭 → 모달) ── */}
      <motion.button
        type="button"
        whileHover={{ y: -2 }}
        transition={{ type: 'spring', stiffness: 280, damping: 26 }}
        onClick={() => setModalOpen(true)}
        className={cn(
          'group w-full overflow-hidden rounded-card border bg-card p-4 text-left shadow-card',
          'transition-colors hover:border-hanwha/50',
          meta.ring,
        )}
        aria-label="AI 위원회 결과 자세히 보기"
      >
        {/* 상단 hairline */}
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-60" />

        <div className="mb-2.5 flex items-center justify-between">
          <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
            <Gavel size={12} strokeWidth={2} />
            최신 AI 위원회
          </div>
          <div className="flex items-center gap-1.5">
            {data.is_seed && <Badge tone="neutral">표본</Badge>}
            <ChevronRight
              size={14}
              strokeWidth={2}
              className="text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-hanwha"
            />
          </div>
        </div>

        <div className={cn('flex items-center gap-3 rounded-chip border p-3', meta.ring, meta.surface)}>
          <div className={cn('grid h-9 w-9 shrink-0 place-items-center rounded-pill', meta.text)}>
            {meta.icon}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <span className="truncate font-display text-sm font-bold text-beige">
                {displayTicker}
              </span>
              <Badge tone={meta.tone} dot className="shrink-0 text-[11px]">
                {meta.label}
              </Badge>
            </div>
            <p className="mt-0.5 font-mono text-[10px] text-muted">
              클릭하여 심의 과정 + 리포트 보기
            </p>
          </div>
        </div>
      </motion.button>

      {/* ── 모달 ── */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={
          <div className="flex items-center gap-2">
            <Building2 size={15} className="text-hanwha" />
            AI 투자운용위원회 · {displayTicker}
          </div>
        }
        maxWidth="max-w-4xl"
      >
        <div className="space-y-6">
          {/* 최종 결정 배너 */}
          <div
            className={cn(
              'flex flex-wrap items-center justify-between gap-4 rounded-card border p-4',
              meta.ring,
              meta.surface,
            )}
          >
            <div className="flex items-center gap-3">
              <div className={cn('grid h-11 w-11 shrink-0 place-items-center rounded-pill', meta.text)}>
                {meta.icon}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-display text-lg font-bold text-beige">{displayTicker}</span>
                  {data.ticker && data.ticker !== data.input && (
                    <span className="font-mono text-sm tabular-nums text-muted">{data.ticker}</span>
                  )}
                  {data.is_seed && <Badge tone="neutral">표본</Badge>}
                </div>
                <p className="mt-0.5 text-xs text-muted">AI 투자위원회 최종 판단</p>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1">
              <span className="font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                최종 결정
              </span>
              <div className={cn('flex items-center gap-1.5 font-display text-xl font-bold', meta.text)}>
                <CheckCircle2 size={18} className="opacity-80" />
                {meta.label}
              </div>
            </div>
          </div>

          {/* decision raw */}
          {data.decision && (
            <div className="rounded-card border border-line bg-card-2/30 px-4 py-3">
              <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
                Decision Raw
              </div>
              <p className="font-mono text-sm leading-relaxed text-greige">{data.decision}</p>
            </div>
          )}

          {/* 4단계 파이프라인 완료 시각화 */}
          <div>
            <div className="mb-3 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
              심의 과정 · 4단계 14에이전트 완료
            </div>
            <PipelineCompleted />
          </div>

          {/* 9개 리포트 탭 */}
          <div>
            <div className="mb-3 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
              심의 리포트
            </div>
            {availableTabs.length === 0 ? (
              <EmptyState
                icon={<MessagesSquare size={18} strokeWidth={1.75} />}
                title="리포트 없음"
                description="이번 심의에서 생성된 세부 리포트가 없습니다."
              />
            ) : (
              <Card noPadding>
                {/* 탭 바 */}
                <div className="relative flex gap-1 overflow-x-auto border-b border-line px-3">
                  {availableTabs.map(t => {
                    const isActive = activeReport === t.id
                    return (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setActiveReport(t.id)}
                        className={cn(
                          'relative inline-flex items-center gap-1.5 whitespace-nowrap px-3 py-2.5 text-xs font-semibold transition-colors',
                          isActive ? 'text-hanwha' : 'text-muted hover:text-beige',
                        )}
                      >
                        {t.icon}
                        {t.label}
                        {isActive && (
                          <motion.span
                            layoutId="committeeWidgetReportTab"
                            className="absolute inset-x-2 -bottom-px h-0.5 rounded-pill bg-hanwha"
                            transition={{ type: 'spring', stiffness: 320, damping: 30 }}
                          />
                        )}
                      </button>
                    )
                  })}
                </div>

                {/* 리포트 본문 */}
                <AnimatePresence mode="wait">
                  <motion.div
                    key={activeReport}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.16 }}
                    className="px-5 py-5"
                  >
                    {data.reports?.[activeReport] ? (
                      <Markdown>{data.reports[activeReport]}</Markdown>
                    ) : (
                      <EmptyState
                        title="해당 리포트 없음"
                        description="선택한 항목의 리포트가 비어 있습니다."
                      />
                    )}
                  </motion.div>
                </AnimatePresence>
              </Card>
            )}
          </div>
        </div>
      </Modal>
    </>
  )
}

export default CommitteeLatestWidget
