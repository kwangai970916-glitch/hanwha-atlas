/**
 * 내 종목 오늘 — AI 위원회 결정 (/api/committee/latest)
 * 손익 → 위원회 → 시황 루프를 시각적으로 닫는 요약 카드.
 */
import { useCallback, useEffect, useState } from 'react'
import { RefreshCw, Gavel, ArrowUpRight, ArrowDownRight, MinusCircle } from 'lucide-react'
import { Badge, Skeleton } from '../ui'
import { cn } from '../../lib/utils'
import {
  hasText,
  classifyDecision,
  summarizeDecision,
  VERDICT_STYLE,
} from './utils'
import type { CommitteeLatest } from './types'

export function CommitteeLatestCard({ apiBase }: { apiBase: string }) {
  const [data, setData] = useState<CommitteeLatest | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetch(`${apiBase}/api/committee/latest`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: CommitteeLatest) => {
        setData(d)
        setFailed(false)
      })
      .catch(() => setFailed(true))
      .finally(() => setLoading(false))
  }, [apiBase])

  useEffect(() => {
    load()
  }, [load])

  if (loading && !data) {
    return <Skeleton className="h-[148px] w-full rounded-card" />
  }

  if (failed || !data || data.available === false) return null

  const ticker = hasText(data.ticker ?? undefined)
    ? data.ticker!.trim()
    : hasText(data.input ?? undefined)
      ? data.input!.trim()
      : '대상 종목'
  const verdict = classifyDecision(data.decision)
  const meta = VERDICT_STYLE[verdict]
  const summary = summarizeDecision(data.reports?.final_trade_decision)
  const isSeed = data.is_seed === true

  const VerdictIcon =
    verdict === 'buy'
      ? ArrowUpRight
      : verdict === 'sell'
        ? ArrowDownRight
        : MinusCircle

  return (
    <div className="relative overflow-hidden rounded-card border border-line bg-card bg-warm-radial p-5 shadow-card">
      <span className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-hanwha to-transparent opacity-70" />
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-hanwha">
          <Gavel size={13} strokeWidth={2} />
          내 종목 오늘 · AI 위원회 결정
        </div>
        <div className="flex items-center gap-1.5">
          {isSeed && <Badge tone="neutral">표본</Badge>}
          <button
            type="button"
            onClick={load}
            className="grid h-6 w-6 place-items-center rounded-chip text-muted transition-colors hover:bg-card-2 hover:text-hanwha"
            aria-label="위원회 결정 새로고침"
          >
            <RefreshCw size={13} strokeWidth={2} />
          </button>
        </div>
      </div>

      <div
        className={cn(
          'mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 rounded-chip border p-4',
          meta.ring,
          meta.surface,
        )}
      >
        <div className={cn('grid h-11 w-11 shrink-0 place-items-center rounded-chip', meta.text)}>
          <VerdictIcon size={20} strokeWidth={verdict === 'hold' ? 2.2 : 2.4} />
        </div>
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="truncate font-display text-xl font-bold tracking-tight text-beige">
              {ticker}
            </h3>
            <Badge tone={meta.tone} dot className="shrink-0 text-[12px]">
              {meta.label}
            </Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted">
            AI 투자위원회 최종 판단
            {hasText(data.decision ?? undefined) && (
              <>
                {' · '}
                <span className={cn('font-mono font-semibold', meta.text)}>
                  {data.decision!.trim()}
                </span>
              </>
            )}
          </p>
        </div>
      </div>

      {summary ? (
        <p className="mt-3 line-clamp-3 text-sm leading-relaxed text-greige">{summary}</p>
      ) : (
        <p className="mt-3 text-sm text-muted">최종 결정 요약을 수신하지 못했습니다.</p>
      )}
    </div>
  )
}
