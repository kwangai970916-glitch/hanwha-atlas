/**
 * BriefingLatestWidget
 * 마운트 시 GET /api/briefing/latest → 작은 카드 위젯
 * 클릭 → Modal: 9섹션 카드 + 원본 PNG 접이식
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import {
  Activity,
  ChevronRight,
  ChevronDown,
  Globe,
  Compass,
  Target,
  Newspaper,
  TrendingUp,
  TrendingDown,
  ImageIcon,
  Download,
} from 'lucide-react'
import { Markdown } from '../Markdown'
import { Badge, Card, EmptyState, ErrorState, Modal, Skeleton } from '../ui'
import { cn } from '../../lib/utils'

// ── 타입 ─────────────────────────────────────────────────────────────────────
type Sections = {
  title?: string
  stance?: string
  key_issue?: string
  bull_case?: string
  bear_case?: string
  macro_flow?: string
  kr_outlook?: string
  strategy?: string
  news_flow?: string
}

type BriefingLatest = {
  available?: boolean
  slot?: string
  sections?: Sections
  png_path?: string
  interactive?: unknown
  from_history?: boolean
}

type LoadState = 'loading' | 'ready' | 'unavailable' | 'error'

// ── 슬롯 라벨 ────────────────────────────────────────────────────────────────
const SLOT_LABEL: Record<string, string> = {
  premarket: '장전 브리핑',
  intraday: '장중 브리핑',
  close: '장마감 브리핑',
}

// ── stance → Badge 톤 (한국 관례) ────────────────────────────────────────────
function stanceTone(stance?: string): { tone: 'up' | 'down' | 'neutral' | 'hanwha'; label: string } {
  const s = (stance ?? '').toUpperCase()
  if (/BULL|RISK[- ]?ON|강세|매수|OVERWEIGHT|POSITIVE/.test(s))
    return { tone: 'up', label: stance || '강세' }
  if (/BEAR|RISK[- ]?OFF|약세|매도|UNDERWEIGHT|NEGATIVE|CAUTION/.test(s))
    return { tone: 'down', label: stance || '약세' }
  if (/NEUTRAL|중립|HOLD/.test(s)) return { tone: 'neutral', label: stance || '중립' }
  return { tone: 'hanwha', label: stance || '—' }
}

const hasText = (v?: string) => typeof v === 'string' && v.trim().length > 0

// ── 텍스트 섹션 카드 (모달용) ─────────────────────────────────────────────────
function TextSection({
  icon,
  eyebrow,
  title,
  body,
}: {
  icon: ReactNode
  eyebrow: string
  title: string
  body?: string
}) {
  return (
    <Card
      eyebrow={
        <span className="inline-flex items-center gap-1.5">
          {icon}
          {eyebrow}
        </span>
      }
      title={title}
    >
      {hasText(body) ? (
        <Markdown>{body!}</Markdown>
      ) : (
        <p className="text-sm text-muted">데이터가 없습니다.</p>
      )}
    </Card>
  )
}

// ── PNG 접이식 (모달용) ───────────────────────────────────────────────────────
function PngAccordion({ pngUrl, slot }: { pngUrl: string; slot: string }) {
  const [open, setOpen] = useState(false)
  const [loaded, setLoaded] = useState(false)
  const [failed, setFailed] = useState(false)

  useEffect(() => { setLoaded(false); setFailed(false) }, [pngUrl])

  return (
    <Card
      eyebrow="Original Report"
      title="원본 PNG 리포트"
      action={
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOpen(v => !v)}
            className="inline-flex items-center gap-1.5 rounded-chip border border-line bg-card-2 px-3 py-1.5 text-xs font-semibold text-beige transition-colors hover:border-hanwha hover:text-hanwha"
          >
            <ChevronDown
              size={14}
              strokeWidth={2}
              className={cn('transition-transform', open && 'rotate-180')}
            />
            {open ? '접기' : '미리보기'}
          </button>
          <a
            href={pngUrl}
            download={`briefing-${slot}.png`}
            className="inline-flex items-center gap-1.5 rounded-chip border border-line bg-card-2 px-3 py-1.5 text-xs font-semibold text-beige transition-colors hover:border-hanwha hover:text-hanwha"
          >
            <Download size={14} strokeWidth={2} />
            다운로드
          </a>
        </div>
      }
    >
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="overflow-hidden"
          >
            <div className="relative overflow-hidden rounded-card border border-line bg-canvas">
              {!loaded && !failed && <Skeleton className="aspect-[4/3] w-full" />}
              {failed ? (
                <div className="p-6">
                  <ErrorState
                    title="이미지를 불러오지 못했습니다"
                    message="원본 PNG 응답에 실패했습니다."
                    className="border-0 bg-transparent px-0 py-4"
                  />
                </div>
              ) : (
                <motion.img
                  key={pngUrl}
                  src={pngUrl}
                  alt="시황 리포트 PNG"
                  onLoad={() => setLoaded(true)}
                  onError={() => setFailed(true)}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: loaded ? 1 : 0 }}
                  transition={{ duration: 0.3 }}
                  className={loaded ? 'block w-full' : 'absolute inset-0 h-0 w-0 opacity-0'}
                />
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
      {!open && (
        <div className="flex items-center gap-2 text-xs text-muted">
          <ImageIcon size={13} strokeWidth={1.9} className="text-blue" />
          생성 완료 · PNG 미리보기 버튼으로 확인하세요.
        </div>
      )}
    </Card>
  )
}

// ── 메인 컴포넌트 ────────────────────────────────────────────────────────────
export function BriefingLatestWidget({ apiBase }: { apiBase: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [data, setData] = useState<BriefingLatest | null>(null)
  const [modalOpen, setModalOpen] = useState(false)

  const load = useCallback(() => {
    setState('loading')
    fetch(`${apiBase}/api/briefing/latest`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: BriefingLatest) => {
        setData(d)
        setState(d.available === false ? 'unavailable' : 'ready')
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
        title="시황 브리핑 조회 실패"
        onRetry={load}
        className="rounded-card border border-line bg-card"
      />
    )
  }

  // ── 미생성 ──
  if (state === 'unavailable' || !data) {
    return (
      <div className="flex flex-col gap-2 rounded-card border border-line bg-card px-4 py-4">
        <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
          <Activity size={13} />
          최신 시황 브리핑
        </div>
        <EmptyState
          icon={<Activity size={18} strokeWidth={1.75} />}
          title="시황 미생성"
          description="시황에이전트 탭에서 브리핑을 생성해 주세요."
          className="border-0 bg-transparent px-0 py-3"
        />
      </div>
    )
  }

  const slotLabel = SLOT_LABEL[data.slot ?? ''] ?? data.slot ?? '브리핑'
  const sections = data.sections
  const st = stanceTone(sections?.stance)
  const titleText = hasText(sections?.title) ? sections!.title! : slotLabel
  const pngUrl = data.png_path ? `${apiBase}/api/briefing/${data.slot}/png` : null
  const isHistoryOnly = data.from_history === true && !sections

  return (
    <>
      {/* ── 위젯 카드 ── */}
      <motion.button
        type="button"
        whileHover={{ y: -2 }}
        transition={{ type: 'spring', stiffness: 280, damping: 26 }}
        onClick={() => setModalOpen(true)}
        className="group relative w-full overflow-hidden rounded-card border border-line bg-card p-4 text-left shadow-card transition-colors hover:border-hanwha/50"
        aria-label="최신 시황 브리핑 자세히 보기"
      >
        <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-60" />

        <div className="mb-2.5 flex items-center justify-between">
          <div className="flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
            <Activity size={12} strokeWidth={2} />
            최신 시황 브리핑
          </div>
          <div className="flex items-center gap-1.5">
            <Badge tone="neutral">{slotLabel}</Badge>
            <ChevronRight
              size={14}
              strokeWidth={2}
              className="text-muted transition-transform group-hover:translate-x-0.5 group-hover:text-hanwha"
            />
          </div>
        </div>

        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1">
            <p className="truncate font-display text-sm font-bold text-beige">{titleText}</p>
            {sections?.stance && (
              <div className="mt-1">
                <Badge tone={st.tone} dot className="text-[11px]">
                  {st.label}
                </Badge>
              </div>
            )}
            <p className="mt-1 font-mono text-[10px] text-muted">
              클릭하여 9섹션 시황 리포트 보기
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
            <Activity size={15} className="text-hanwha" />
            {slotLabel} · 시황 브리핑
            {isHistoryOnly && <Badge tone="neutral">이력</Badge>}
          </div>
        }
        maxWidth="max-w-4xl"
      >
        <div className="space-y-6">
          {/* 이력 전용(PNG+요약만) */}
          {isHistoryOnly ? (
            <>
              <EmptyState
                icon={<ImageIcon size={20} strokeWidth={1.75} />}
                title="섹션 데이터 없음"
                description="이력 브리핑은 원본 PNG만 제공됩니다."
              />
              {pngUrl && <PngAccordion pngUrl={pngUrl} slot={data.slot ?? ''} />}
            </>
          ) : sections ? (
            <>
              {/* 헤더 카드 */}
              <div className="relative overflow-hidden rounded-card border border-line bg-card p-5 shadow-card">
                <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-70" />
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="mb-1.5 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.1em] text-hanwha">
                      <span className="h-px w-5 bg-hanwha/60" />
                      {slotLabel}
                    </div>
                    <h3 className="font-display text-xl font-bold tracking-tight text-beige">
                      {titleText}
                    </h3>
                  </div>
                  {sections.stance && (
                    <Badge tone={st.tone} dot className="shrink-0 text-[12px]">
                      {st.label}
                    </Badge>
                  )}
                </div>
                {hasText(sections.key_issue) && (
                  <div className="mt-4 rounded-chip border border-line bg-card-2/40 p-4">
                    <div className="mb-1 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-muted">
                      Key Issue · 핵심 이슈
                    </div>
                    <Markdown>{sections.key_issue!}</Markdown>
                  </div>
                )}
              </div>

              {/* Bull / Bear */}
              {(hasText(sections.bull_case) || hasText(sections.bear_case)) && (
                <div className="grid gap-4 sm:grid-cols-2">
                  {hasText(sections.bull_case) && (
                    <div className="rounded-card border border-up/25 bg-up/[0.05] p-4">
                      <div className="mb-2 flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-up">
                        <TrendingUp size={13} strokeWidth={2.2} />
                        Bull Case · 상승 논거
                      </div>
                      <Markdown>{sections.bull_case!}</Markdown>
                    </div>
                  )}
                  {hasText(sections.bear_case) && (
                    <div className="rounded-card border border-down/25 bg-down/[0.05] p-4">
                      <div className="mb-2 flex items-center gap-1.5 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-down">
                        <TrendingDown size={13} strokeWidth={2.2} />
                        Bear Case · 하락 논거
                      </div>
                      <Markdown>{sections.bear_case!}</Markdown>
                    </div>
                  )}
                </div>
              )}

              {/* 4개 텍스트 섹션 */}
              <div className="grid gap-4 lg:grid-cols-2">
                <TextSection
                  icon={<Globe size={14} strokeWidth={2} className="text-blue" />}
                  eyebrow="Macro Flow"
                  title="글로벌 매크로 흐름"
                  body={sections.macro_flow}
                />
                <TextSection
                  icon={<Compass size={14} strokeWidth={2} className="text-purple" />}
                  eyebrow="KR Outlook"
                  title="국내 증시 전망"
                  body={sections.kr_outlook}
                />
                <TextSection
                  icon={<Target size={14} strokeWidth={2} className="text-hanwha" />}
                  eyebrow="Strategy"
                  title="투자 전략"
                  body={sections.strategy}
                />
                <TextSection
                  icon={<Newspaper size={14} strokeWidth={2} className="text-greige" />}
                  eyebrow="News Flow"
                  title="주요 뉴스 흐름"
                  body={sections.news_flow}
                />
              </div>

              {/* 원본 PNG */}
              {pngUrl && <PngAccordion pngUrl={pngUrl} slot={data.slot ?? ''} />}
            </>
          ) : (
            <EmptyState
              icon={<Activity size={20} strokeWidth={1.75} />}
              title="섹션 데이터 없음"
              description="브리핑 섹션을 수신하지 못했습니다."
            />
          )}
        </div>
      </Modal>
    </>
  )
}

export default BriefingLatestWidget
