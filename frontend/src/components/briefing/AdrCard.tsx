/**
 * ADR 라인 차트 (있으면)
 */
import { useMemo } from 'react'
import { LineChart as LineChartIcon } from 'lucide-react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { Badge, Card, EmptyState } from '../ui'
import { C } from './utils'
import type { Interactive } from './types'

export function AdrCard({ interactive }: { interactive?: Interactive }) {
  const series = useMemo(() => {
    const hist = interactive?.adr_history ?? []
    return hist
      .filter((e) => e && (e.kospi != null || e.kosdaq != null))
      .map((e) => ({
        date: (e.date ?? '').slice(5), // MM-DD
        kospi: typeof e.kospi === 'number' ? e.kospi : null,
        kosdaq: typeof e.kosdaq === 'number' ? e.kosdaq : null,
      }))
  }, [interactive])

  const latest = interactive?.adr_latest
  const hasData = series.length > 0

  return (
    <Card
      eyebrow={
        <span className="inline-flex items-center gap-1.5">
          <LineChartIcon size={14} strokeWidth={2} />
          ADR
        </span>
      }
      title="등락비율(ADR) 추이"
      action={
        latest && (typeof latest.kospi === 'number' || typeof latest.kosdaq === 'number') ? (
          <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums">
            {typeof latest.kospi === 'number' && (
              <Badge tone="up">KOSPI {latest.kospi.toFixed(1)}</Badge>
            )}
            {typeof latest.kosdaq === 'number' && (
              <Badge tone="down">KOSDAQ {latest.kosdaq.toFixed(1)}</Badge>
            )}
          </div>
        ) : undefined
      }
    >
      {!hasData ? (
        <EmptyState
          icon={<LineChartIcon size={20} strokeWidth={1.75} />}
          title="ADR 데이터 없음"
          description="ADR 시계열(adr_history)이 비어 있습니다."
          className="border-0 bg-transparent px-0 py-8"
        />
      ) : (
        <div>
          <div className="mb-3 flex flex-wrap items-center gap-x-4 gap-y-1 px-1 font-mono text-[11px] text-muted">
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full bg-up" />
              KOSPI ADR
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span className="h-0.5 w-4 rounded-full bg-down" />
              KOSDAQ ADR
            </span>
            <span className="ml-auto">100 = 등락 균형 · 120↑ 과열 / 80↓ 침체</span>
          </div>
          <ResponsiveContainer width="100%" height={260}>
            <LineChart data={series} margin={{ top: 6, right: 14, left: 4, bottom: 0 }}>
              <CartesianGrid stroke={C.line} strokeOpacity={0.35} vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={{ stroke: C.line }}
                minTickGap={40}
              />
              <YAxis
                width={40}
                domain={['auto', 'auto']}
                tick={{ fill: C.muted, fontSize: 10, fontFamily: 'Pretendard, Noto Sans KR' }}
                tickLine={false}
                axisLine={false}
              />
              <ReferenceLine y={100} stroke={C.muted} strokeDasharray="4 3" strokeOpacity={0.6} />
              <Tooltip
                labelStyle={{
                  color: C.greige,
                  fontFamily: 'Pretendard, Noto Sans KR',
                  fontSize: 11,
                }}
                contentStyle={{
                  background: C.card,
                  border: `1px solid ${C.line}`,
                  borderRadius: 11,
                  fontSize: 12,
                  fontFamily: 'Pretendard, Noto Sans KR',
                  color: C.beige,
                }}
                cursor={{ stroke: C.line, strokeWidth: 1 }}
                formatter={(value: unknown, name: unknown) => {
                  const v = value as number | null
                  const label = name === 'kospi' ? 'KOSPI ADR' : 'KOSDAQ ADR'
                  return [v == null ? '—' : v.toFixed(1), label]
                }}
              />
              <Line
                type="monotone"
                dataKey="kospi"
                name="kospi"
                stroke={C.up}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3.5, fill: C.up }}
                connectNulls
              />
              <Line
                type="monotone"
                dataKey="kosdaq"
                name="kosdaq"
                stroke={C.down}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 3.5, fill: C.down }}
                connectNulls
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  )
}
