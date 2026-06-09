/**
 * 다음 자동생성 카운트다운 (/api/briefing/schedule)
 */
import { useCallback, useEffect, useState } from 'react'
import { Clock } from 'lucide-react'
import { Skeleton } from '../ui'
import { cn } from '../../lib/utils'
import { formatCountdown, SLOT_LABEL } from './utils'
import type { ScheduleItem } from './types'

export function ScheduleRail({ apiBase }: { apiBase: string }) {
  const [slots, setSlots] = useState<ScheduleItem[] | null>(null)
  const [failed, setFailed] = useState(false)
  const [now, setNow] = useState(() => Date.now())

  const load = useCallback(() => {
    fetch(`${apiBase}/api/briefing/schedule`)
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then((d: { slots?: ScheduleItem[] }) => {
        setSlots(Array.isArray(d.slots) ? d.slots : [])
        setFailed(false)
      })
      .catch(() => setFailed(true))
  }, [apiBase])

  useEffect(() => {
    load()
    const t = setInterval(load, 60_000)
    return () => clearInterval(t)
  }, [load])

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(t)
  }, [])

  if (failed && !slots) return null
  if (!slots) {
    return (
      <div className="grid gap-3 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-[68px] w-full rounded-card" />
        ))}
      </div>
    )
  }
  if (slots.length === 0) return null

  const withRemaining = slots
    .map((s) => ({
      ...s,
      remaining: Math.max(0, Math.round(s.next_epoch - now / 1000)),
    }))
    .sort((a, b) => a.remaining - b.remaining)
  const soonest = withRemaining[0]?.slot

  return (
    <div className="rounded-card border border-line bg-card bg-warm-radial p-4 shadow-card">
      <div className="mb-3 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-hanwha">
        <Clock size={13} strokeWidth={2} />
        다음 자동 생성 예정
      </div>
      <div className="grid gap-3 sm:grid-cols-3">
        {withRemaining.map((s) => {
          const isSoonest = s.slot === soonest
          return (
            <div
              key={s.slot}
              className={cn(
                'flex flex-col gap-1 rounded-chip border px-3.5 py-2.5 transition-colors',
                isSoonest
                  ? 'border-hanwha/40 bg-hanwha/[0.06]'
                  : 'border-line bg-card-2/40',
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="font-display text-sm font-bold text-beige">
                  {SLOT_LABEL[s.slot] ?? s.slot}
                </span>
                <span className="font-mono text-[11px] font-semibold tabular-nums text-greige">
                  {s.label}
                </span>
              </div>
              <span
                className={cn(
                  'font-mono text-xs font-semibold tabular-nums',
                  isSoonest ? 'text-hanwha' : 'text-muted',
                )}
              >
                {formatCountdown(s.remaining)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
