/**
 * BriefingReport — ReportEnvelope 렌더러
 * 슬롯 공통 envelope 을 warm-dark 하우스 스타일로 표시.
 */
import { Card, Badge } from '../ui'
import { cn } from '../../lib/utils'
import type { ReportEnvelope, ReportBlock, KvItem } from './types'

// ── Stance pill ───────────────────────────────────────────────────────────────

type Stance = ReportEnvelope['stance']

const STANCE_CLASS: Record<Stance, string> = {
  'RISK-ON':  'bg-up/10  text-up   border border-up/25',
  'NEUTRAL':  'bg-card-2 text-greige border border-line',
  'RISK-OFF': 'bg-down/10 text-down border border-down/25',
}

function StancePill({ stance }: { stance: Stance }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-pill px-2.5 py-0.5',
        'font-mono text-[11px] font-semibold uppercase tracking-[0.04em]',
        STANCE_CLASS[stance],
      )}
    >
      {stance}
    </span>
  )
}

// ── Block renderers ───────────────────────────────────────────────────────────

function ParagraphBlock({ body }: { body: string | string[] | KvItem[] }) {
  const text =
    typeof body === 'string'
      ? body
      : Array.isArray(body)
        ? typeof body[0] === 'string'
          ? (body as string[]).join(' ')
          : (body as KvItem[]).map((i) => `${i.k}: ${i.v}`).join(' ')
        : ''
  return <p className="text-sm leading-relaxed text-greige">{text}</p>
}

function BulletsBlock({ body }: { body: string | string[] | KvItem[] }) {
  const items: string[] =
    typeof body === 'string'
      ? [body]
      : Array.isArray(body)
        ? typeof body[0] === 'string'
          ? (body as string[])
          : (body as KvItem[]).map((i) => `${i.k}: ${i.v}`)
        : []
  return (
    <ul className="space-y-1.5">
      {items.map((item, idx) => (
        <li
          key={idx}
          className="flex items-start gap-2 text-sm text-greige"
        >
          <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-hanwha" />
          {item}
        </li>
      ))}
    </ul>
  )
}

function KvBlock({ body }: { body: string | string[] | KvItem[] }) {
  const rows: KvItem[] =
    typeof body === 'string'
      ? [{ k: body, v: '' }]
      : Array.isArray(body)
        ? typeof body[0] === 'string'
          ? (body as string[]).map((s) => ({ k: s, v: '' }))
          : (body as KvItem[])
        : []
  return (
    <div className="space-y-1.5">
      {rows.map((item, idx) => {
        // 값이 수치가 아니라 긴 해석 문장이면 우측정렬 모노폰트 대신 세로 배치로 가독성 확보
        const isLong = String(item.v ?? '').length > 28
        const toneClass =
          item.tone === 'up' ? 'text-up' : item.tone === 'down' ? 'text-down' : 'text-beige'
        return (
          <div
            key={idx}
            className={cn(
              'rounded-[10px] border border-line/45 bg-canvas/25 px-2.5 py-1.5',
              isLong ? 'space-y-0.5' : 'flex items-center justify-between gap-3',
            )}
          >
            <span className="text-xs text-greige">{item.k}</span>
            <span
              className={cn(
                isLong
                  ? 'block text-xs leading-relaxed'
                  : 'font-mono text-xs font-semibold tabular-nums',
                toneClass,
              )}
            >
              {item.v}
            </span>
          </div>
        )
      })}
    </div>
  )
}

function BlockRenderer({ block }: { block: ReportBlock }) {
  return (
    <div>
      <div className="mb-2 font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
        {block.label}
      </div>
      {block.type === 'paragraph' && <ParagraphBlock body={block.body} />}
      {block.type === 'bullets' && <BulletsBlock body={block.body} />}
      {block.type === 'kv' && <KvBlock body={block.body} />}
    </div>
  )
}

// ── Timestamp formatter ───────────────────────────────────────────────────────

function formatTs(generatedAt: number | null, asOf?: string): string {
  if (asOf) return asOf
  if (!generatedAt) return ''
  try {
    return new Date(generatedAt).toLocaleString('ko-KR', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

// ── Main component ────────────────────────────────────────────────────────────

export type BriefingReportProps = {
  report: ReportEnvelope
  generatedAt: number | null
}

export function BriefingReport({ report, generatedAt }: BriefingReportProps) {
  const ts = formatTs(generatedAt, report.as_of)

  return (
    <Card eyebrow="Briefing Report" className="space-y-0">
      {/* Header */}
      <div className="flex flex-wrap items-center gap-2 px-5 pb-3">
        <Badge tone="hanwha">{report.persona}</Badge>
        <StancePill stance={report.stance} />
        <h2 className="flex-1 font-display text-base font-bold tracking-tight text-beige">
          {report.title}
        </h2>
        {ts && (
          <span className="font-mono text-[10px] text-muted">{ts}</span>
        )}
      </div>

      {/* Headline callout */}
      <div className="mx-5 mb-4 border-l-2 border-[#F37321] pl-3">
        <p className="text-sm font-semibold text-beige">{report.headline}</p>
      </div>

      {/* Blocks grid */}
      <div className="grid gap-4 px-5 pb-5 sm:grid-cols-2">
        {report.blocks.map((block, idx) => (
          <div
            key={block.id}
            className={cn(
              'rounded-[14px] border border-line/60 bg-card-2/40 p-3',
              idx === 0 && 'sm:col-span-2',
            )}
          >
            <BlockRenderer block={block} />
          </div>
        ))}
      </div>
    </Card>
  )
}

export default BriefingReport
