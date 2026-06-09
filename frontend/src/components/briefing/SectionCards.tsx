/**
 * 9섹션 인터랙티브 카드
 */
import type { ReactNode } from 'react'
import {
  Compass,
  Globe,
  Newspaper,
  RadioTower,
  ScanLine,
  Target,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { Badge, Card, EmptyState } from '../ui'
import { Markdown } from '../Markdown'
import { cn } from '../../lib/utils'
import { hasText, stanceTone, SLOT_LABEL, LLM_MODEL } from './utils'
import type { Sections, SlotId } from './types'

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

function ResearchBullets({ body }: { body?: string }) {
  if (!hasText(body)) return <p className="text-sm text-muted">데이터가 없습니다.</p>
  const lines = body!
    .split('\n')
    .map((line) => line.trim().replace(/^[-•·]\s*/, ''))
    .filter(Boolean)

  return (
    <div className="space-y-2.5">
      {lines.map((line, idx) => {
        const match = line.match(/^(팩트|판단|액션|트리거|레벨|모니터링)\s*[:：]\s*(.*)$/)
        const label = match?.[1]
        const text = match?.[2] ?? line
        return (
          <div
            key={`${line}-${idx}`}
            className="group grid grid-cols-[76px_minmax(0,1fr)] gap-3 rounded-[14px] border border-line/60 bg-canvas/35 px-3.5 py-3 shadow-inset"
          >
            <div className="flex items-start gap-2">
              <span className="mt-1.5 h-1.5 w-1.5 rounded-full bg-hanwha shadow-[0_0_0_4px_rgba(243,115,33,0.12)]" />
              <span className="font-mono text-[11px] font-extrabold tracking-[0.06em] text-hanwha">
                {label ?? `POINT ${idx + 1}`}
              </span>
            </div>
            <p className="text-[13.5px] leading-7 text-beige/92">{text}</p>
          </div>
        )
      })}
    </div>
  )
}

function ScenarioPanel({
  tone,
  title,
  body,
}: {
  tone: 'bull' | 'bear'
  title: string
  body?: string
}) {
  const bullish = tone === 'bull'
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-[20px] border p-4',
        bullish
          ? 'border-up/35 bg-up/[0.045]'
          : 'border-down/35 bg-down/[0.045]',
      )}
    >
      <span
        className={cn(
          'absolute inset-x-0 top-0 h-1',
          bullish ? 'bg-up' : 'bg-down',
        )}
      />
      <div className="mb-3 flex items-center justify-between gap-3">
        <div
          className={cn(
            'inline-flex items-center gap-2 font-mono text-[11px] font-extrabold uppercase tracking-[0.12em]',
            bullish ? 'text-up' : 'text-down',
          )}
        >
          {bullish ? <TrendingUp size={15} /> : <TrendingDown size={15} />}
          {title}
        </div>
        <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
          Scenario Map
        </span>
      </div>
      <ResearchBullets body={body} />
    </div>
  )
}

export function SectionCards({
  sections,
  slot,
  generatedAt,
}: {
  sections?: Sections
  slot: SlotId
  generatedAt?: number | null
}) {
  const genLabel = (() => {
    if (!generatedAt) return null
    const d = new Date(generatedAt)
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${hh}:${mi}`
  })()

  if (!sections) {
    return (
      <EmptyState
        title="섹션 데이터 없음"
        description="LLM 시황 섹션을 수신하지 못했습니다. 원본 PNG 리포트를 확인해 주세요."
      />
    )
  }

  const s = stanceTone(sections.stance)
  const title =
    hasText(sections.title) ? sections.title!.trim() : `${SLOT_LABEL[slot] ?? slot} 시황`
  const hasBull = hasText(sections.bull_case)
  const hasBear = hasText(sections.bear_case)

  return (
    <div className="space-y-5">
      {/* ── 리서치 터미널 헤더 ── */}
      <div className="relative overflow-hidden rounded-[28px] border border-hanwha/25 bg-[#211815] shadow-card">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_12%_0%,rgba(243,115,33,0.18),transparent_34%),linear-gradient(135deg,rgba(247,241,233,0.06),transparent_42%)]" />
        <div className="absolute inset-y-0 left-0 w-1.5 bg-hanwha" />
        <div className="relative grid gap-0 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="p-6 sm:p-7">
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <Badge tone="hanwha" className="border-hanwha/40 bg-hanwha/15">
                <RadioTower size={12} strokeWidth={2.2} />
                {SLOT_LABEL[slot] ?? slot} Desk Brief
              </Badge>
              <Badge tone={s.tone} dot>
                {s.label}
              </Badge>
              <Badge tone="neutral">LLM {LLM_MODEL}</Badge>
              {genLabel && <Badge tone="blue">Generated {genLabel}</Badge>}
            </div>
            <h3 className="max-w-4xl font-display text-[28px] font-black leading-tight tracking-[-0.045em] text-beige sm:text-[34px]">
              {title}
            </h3>
            <div className="mt-4 flex items-center gap-3 font-mono text-[11px] font-semibold uppercase tracking-[0.18em] text-muted">
              <span className="h-px w-10 bg-hanwha/70" />
              Market regime / flow / action
            </div>
          </div>
          <div className="border-t border-line/60 bg-canvas/25 p-5 lg:border-l lg:border-t-0">
            <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-extrabold uppercase tracking-[0.12em] text-hanwha">
              <ScanLine size={14} />
              핵심 이슈
            </div>
            <ResearchBullets body={sections.key_issue} />
          </div>
        </div>
      </div>

      {/* ── Bull / Bear 시나리오 ── */}
      {(hasBull || hasBear) && (
        <div className="grid gap-4 lg:grid-cols-2">
          {hasBull && <ScenarioPanel tone="bull" title="Bull Case · 상승 경로" body={sections.bull_case} />}
          {hasBear && <ScenarioPanel tone="bear" title="Bear Case · 하방 경로" body={sections.bear_case} />}
        </div>
      )}

      {/* ── macro / kr_outlook / strategy / news_flow ── */}
      <div className="grid gap-5 lg:grid-cols-2">
        <TextSection
          icon={<Globe size={15} strokeWidth={2} className="text-blue" />}
          eyebrow="Macro Flow"
          title="글로벌 매크로 흐름"
          body={sections.macro_flow}
        />
        <TextSection
          icon={<Compass size={15} strokeWidth={2} className="text-purple" />}
          eyebrow="KR Outlook"
          title="국내 증시 전망"
          body={sections.kr_outlook}
        />
        <TextSection
          icon={<Target size={15} strokeWidth={2} className="text-hanwha" />}
          eyebrow="Strategy"
          title="투자 전략"
          body={sections.strategy}
        />
        <TextSection
          icon={<Newspaper size={15} strokeWidth={2} className="text-greige" />}
          eyebrow="News Flow"
          title="주요 뉴스 흐름"
          body={sections.news_flow}
        />
      </div>
    </div>
  )
}
