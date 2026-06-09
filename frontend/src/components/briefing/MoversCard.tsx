/**
 * 상승/하락 종목 + 섹터 등락률
 */
import { TrendingDown, TrendingUp } from 'lucide-react'
import { Card } from '../ui'
import { cn } from '../../lib/utils'
import type { Interactive, NameChange } from './types'

function MoverList({
  title,
  tone,
  rows,
}: {
  title: string
  tone: 'up' | 'down'
  rows: NameChange[]
}) {
  return (
    <div>
      <div
        className={cn(
          'mb-2 flex items-center gap-1 font-mono text-[10px] font-semibold uppercase tracking-[0.06em]',
          tone === 'up' ? 'text-up' : 'text-down',
        )}
      >
        {tone === 'up' ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
        {title}
      </div>
      {rows.length === 0 ? (
        <p className="text-xs text-muted">데이터 없음</p>
      ) : (
        <ul className="space-y-1.5">
          {rows.map((r, i) => (
            <li
              key={`${r.name}-${i}`}
              className="flex items-center justify-between gap-2 rounded-[10px] border border-line/45 bg-canvas/25 px-2.5 py-1.5 text-xs"
            >
              <span className="flex min-w-0 items-center gap-2">
                <span className="font-mono text-[10px] text-muted">{String(i + 1).padStart(2, '0')}</span>
                <span className="truncate text-greige" title={r.name}>
                  {r.name}
                </span>
              </span>
              <span
                className={cn(
                  'shrink-0 font-mono font-semibold tabular-nums',
                  tone === 'up' ? 'text-up' : 'text-down',
                )}
              >
                {r.change >= 0 ? '+' : '−'}
                {Math.abs(r.change).toFixed(2)}%
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export function MoversCard({ interactive }: { interactive?: Interactive }) {
  const gainers = (interactive?.top_gainers ?? []).filter(
    (g) => g && typeof g.change === 'number',
  )
  const losers = (interactive?.top_losers ?? []).filter(
    (g) => g && typeof g.change === 'number',
  )
  const sectors = (interactive?.sector_returns ?? []).filter(
    (s) => s && typeof s.change === 'number' && s.sector,
  )

  const nothing = gainers.length === 0 && losers.length === 0 && sectors.length === 0
  if (nothing) return null

  const maxSectorAbs = sectors.reduce((m, s) => Math.max(m, Math.abs(s.change)), 0)

  return (
    <Card eyebrow="Tape Reading" title="종목 테이프 · 업종 압력">
      <div className="grid gap-5 lg:grid-cols-2">
        {/* 상승/하락 종목 */}
        <div className="grid grid-cols-2 gap-4">
          <MoverList title="상승 상위" tone="up" rows={gainers.slice(0, 8)} />
          <MoverList title="하락 상위" tone="down" rows={losers.slice(0, 8)} />
        </div>

        {/* 섹터 등락률 바 */}
        <div>
          <div className="mb-2 font-mono text-[10px] font-semibold uppercase tracking-[0.06em] text-muted">
            KOSPI 섹터 등락률
          </div>
          {sectors.length === 0 ? (
            <p className="text-sm text-muted">섹터 데이터 없음</p>
          ) : (
            <div className="space-y-2">
              {sectors.slice(0, 10).map((s, i) => {
                const up = s.change >= 0
                const barPct = maxSectorAbs > 0 ? (Math.abs(s.change) / maxSectorAbs) * 100 : 0
                return (
                  <div key={s.sector} className="grid grid-cols-[22px_88px_minmax(0,1fr)_56px] items-center gap-2">
                    <span className="font-mono text-[10px] text-muted">{String(i + 1).padStart(2, '0')}</span>
                    <span
                      className="truncate text-xs text-greige"
                      title={s.sector}
                    >
                      {s.sector}
                    </span>
                    <div className="relative h-3 flex-1 overflow-hidden rounded-pill bg-card-2/60">
                      <span
                        className={cn(
                          'absolute inset-y-0 left-0 rounded-pill',
                          up ? 'bg-up/70' : 'bg-down/70',
                        )}
                        style={{ width: `${barPct}%` }}
                      />
                    </div>
                    <span
                      className={cn(
                        'w-14 shrink-0 text-right font-mono text-xs font-semibold tabular-nums',
                        up ? 'text-up' : 'text-down',
                      )}
                    >
                      {up ? '+' : '−'}
                      {Math.abs(s.change).toFixed(2)}%
                    </span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}
