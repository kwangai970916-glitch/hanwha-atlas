/**
 * RS 4분면 (recharts ScatterChart) — KOSPI / KOSDAQ 토글
 */
import { useMemo, useState } from 'react'
import { ScatterChart as ScatterIcon } from 'lucide-react'
import {
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from 'recharts'
import { Card, EmptyState } from '../ui'
import { cn } from '../../lib/utils'
import { C } from './utils'
import type { Interactive, RsPoint } from './types'

const QUADRANT_TONE: Record<string, string> = {
  리더: C.up,
  숨고르기: C.hanwha,
  단기반등: C.purple,
  약세지속: C.down,
}

type RsTooltipProps = {
  active?: boolean
  payload?: Array<{ payload?: RsPoint }>
}

function RsTooltip({ active, payload }: RsTooltipProps) {
  if (!active || !payload || payload.length === 0) return null
  const p = payload[0]?.payload
  if (!p) return null
  return (
    <div className="rounded-chip border border-line bg-card px-3 py-2 text-xs shadow-card">
      <div className="mb-1 font-display font-bold text-beige">{p.sector}</div>
      <div className="font-mono tabular-nums text-greige">
        1일 RS:{' '}
        <span className={p.rs_1d >= 0 ? 'text-up' : 'text-down'}>{p.rs_1d.toFixed(2)}%</span>
      </div>
      <div className="font-mono tabular-nums text-greige">
        5일 RS:{' '}
        <span className={p.rs_5d >= 0 ? 'text-up' : 'text-down'}>{p.rs_5d.toFixed(2)}%</span>
      </div>
      {p.quadrant && <div className="mt-1 text-hanwha-2">{p.quadrant}</div>}
    </div>
  )
}

export function RsQuadrantCard({ interactive }: { interactive?: Interactive }) {
  const [mkt, setMkt] = useState<'kospi' | 'kosdaq'>('kospi')

  const data = useMemo<RsPoint[]>(() => {
    const src = mkt === 'kospi' ? interactive?.rs_kospi : interactive?.rs_kosdaq
    return (src ?? []).filter(
      (p) => p && typeof p.rs_1d === 'number' && typeof p.rs_5d === 'number',
    )
  }, [interactive, mkt])

  const hasData = data.length > 0
  const axisAbs =
    Math.max(1, ...data.map((d) => Math.max(Math.abs(d.rs_1d), Math.abs(d.rs_5d)))) * 1.15

  return (
    <Card
      eyebrow={
        <span className="inline-flex items-center gap-1.5">
          <ScatterIcon size={14} strokeWidth={2} />
          RS Quadrant
        </span>
      }
      title="섹터 상대강도 4분면"
      action={
        <div className="inline-flex items-center gap-0.5 rounded-pill border border-line bg-card-2/40 p-0.5">
          {(['kospi', 'kosdaq'] as const).map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => setMkt(m)}
              className={cn(
                'rounded-pill px-2.5 py-1 font-mono text-[11px] font-semibold uppercase transition-colors',
                mkt === m ? 'bg-hanwha text-canvas' : 'text-muted hover:text-beige',
              )}
            >
              {m}
            </button>
          ))}
        </div>
      }
    >
      {!hasData ? (
        <EmptyState
          icon={<ScatterIcon size={20} strokeWidth={1.75} />}
          title="RS 데이터 없음"
          description="상대강도 4분면 데이터가 없습니다(휴장/수집 실패 가능)."
          className="border-0 bg-transparent px-0 py-8"
        />
      ) : (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 font-mono text-[11px] text-muted">
            <span>X: 1일 RS(%) · Y: 5일 RS(%)</span>
            {Object.entries(QUADRANT_TONE).map(([q, color]) => (
              <span key={q} className="inline-flex items-center gap-1.5">
                <span className="h-2 w-2 rounded-full" style={{ background: color }} />
                {q}
              </span>
            ))}
          </div>
          <ResponsiveContainer width="100%" height={320}>
            <ScatterChart margin={{ top: 10, right: 16, left: 4, bottom: 8 }}>
              <CartesianGrid stroke={C.line} strokeOpacity={0.35} />
              <XAxis
                type="number"
                dataKey="rs_1d"
                name="1일 RS"
                domain={[-axisAbs, axisAbs]}
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={{ stroke: C.line }}
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <YAxis
                type="number"
                dataKey="rs_5d"
                name="5일 RS"
                domain={[-axisAbs, axisAbs]}
                width={44}
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v: number) => v.toFixed(1)}
              />
              <ZAxis range={[80, 80]} />
              <ReferenceLine x={0} stroke={C.line} strokeOpacity={0.7} />
              <ReferenceLine y={0} stroke={C.line} strokeOpacity={0.7} />
              <Tooltip
                cursor={{ stroke: C.line, strokeWidth: 1, strokeDasharray: '3 3' }}
                contentStyle={{
                  background: C.card,
                  border: `1px solid ${C.line}`,
                  borderRadius: 11,
                  fontSize: 12,
                  fontFamily: 'Pretendard, Noto Sans KR',
                  color: C.beige,
                }}
                content={<RsTooltip />}
              />
              <Scatter data={data} isAnimationActive={false}>
                {data.map((d, i) => (
                  <Cell
                    key={`${d.sector}-${i}`}
                    fill={QUADRANT_TONE[d.quadrant ?? ''] ?? C.greige}
                    fillOpacity={0.85}
                  />
                ))}
              </Scatter>
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
