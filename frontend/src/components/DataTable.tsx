import { useCallback, useEffect, useState } from 'react'
import { Landmark, LineChart, Coins } from 'lucide-react'
import type { ReactNode } from 'react'
import { Card, ChangePill, Skeleton, EmptyState, ErrorState } from './ui'
import { cn } from '../lib/utils'

type Row = { name: string; value?: number | null; chg_1d?: number | null; chg_unit?: 'bp' | '%' | string | null }
type TableData = { bonds: Row[]; equities: Row[]; fx: Row[]; as_of?: string }

const NUM_FMT = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 2 })

function fmtValue(v: number | null | undefined, unit?: string | null): string {
  if (v === null || v === undefined) return '—'
  return new Intl.NumberFormat('ko-KR', {
    minimumFractionDigits: unit === 'bp' ? 3 : 0,
    maximumFractionDigits: unit === 'bp' ? 3 : 2,
  }).format(v)
}

function ValueDisplay({ v, unit, name }: { v?: number | null; unit?: string | null; name?: string }) {
  if (v === null || v === undefined) return <span className="text-muted">—</span>
  const isDollar = name && /WTI|Gold|Gold|천연가스|S&P|Nasdaq|Nikkei|Hang|CSI|VIX|DXY|JPY/.test(name) === false
    && /USD\/KRW|USD\/JPY|DXY/.test(name) === false
    && /WTI|Gold|천연가스/.test(name) === true
  const showDollarPrefix = /WTI|Gold/.test(name ?? '')
  return (
    <span className="font-mono tabular-nums text-beige">
      {showDollarPrefix && <span className="text-muted text-[11px]">$</span>}
      {fmtValue(v, unit)}
    </span>
  )
}

function ChgDisplay({ v, unit }: { v?: number | null; unit?: string | null }) {
  if (v === null || v === undefined) return <span className="text-muted font-mono text-xs">—</span>
  if (unit === 'bp') {
    const cls = v > 0 ? 'text-up' : v < 0 ? 'text-down' : 'text-muted'
    const sign = v > 0 ? '+' : ''
    return <span className={cn('font-mono text-xs font-semibold tabular-nums', cls)}>{sign}{NUM_FMT.format(v)}bp</span>
  }
  return <span className="inline-flex justify-end"><ChangePill value={v} size="sm" /></span>
}

const SECTIONS: { key: keyof Omit<TableData, 'as_of'>; label: string; icon: ReactNode }[] = [
  { key: 'bonds',    label: '채권시장',  icon: <Landmark size={12} strokeWidth={2} /> },
  { key: 'equities', label: '주식시장',  icon: <LineChart size={12} strokeWidth={2} /> },
  { key: 'fx',       label: '상품 · FX', icon: <Coins size={12} strokeWidth={2} /> },
]

export function DataTable({ apiBase }: { apiBase: string }) {
  const [data, setData] = useState<TableData | null>(null)
  const [error, setError] = useState(false)
  const [loading, setLoading] = useState(true)

  const load = useCallback((initial = false) => {
    if (initial) { setLoading(true); setError(false) }
    fetch(`${apiBase}/api/market/table`)
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then((d: TableData) => { setData(d); setLoading(false) })
      .catch(() => {
        setData(prev => { if (!prev) setError(true); return prev })
        setLoading(false)
      })
  }, [apiBase])

  useEffect(() => {
    load(true)
    const id = setInterval(() => load(false), 120_000)
    return () => clearInterval(id)
  }, [load])

  if (loading) {
    return (
      <Card noPadding>
        <div className="space-y-3 p-4">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center justify-between gap-3">
              <Skeleton className="h-3 w-28" />
              <Skeleton className="h-3 w-16" />
              <Skeleton className="h-3 w-12" />
            </div>
          ))}
        </div>
      </Card>
    )
  }

  if (error || !data) {
    return (
      <ErrorState
        title="시장 데이터를 불러오지 못했습니다"
        message="채권 / 주식 / FX 테이블 요청에 실패했습니다."
        onRetry={load}
      />
    )
  }

  const allEmpty = SECTIONS.every(s => (data[s.key]?.length ?? 0) === 0)
  if (allEmpty) {
    return (
      <EmptyState
        title="표시할 시장 데이터가 없습니다"
        description="현재 수신된 채권 / 주식 / FX 데이터가 없습니다."
        action={
          <button onClick={() => load(true)} className="rounded-chip border border-line bg-card-2 px-3.5 py-1.5 text-xs font-semibold text-beige hover:border-hanwha hover:text-hanwha transition-colors">
            새로고침
          </button>
        }
      />
    )
  }

  return (
    <Card
      noPadding
      eyebrow="Cross-Asset"
      title="채권 · 지수 · FX"
      action={
        data.as_of ? (
          <span className="font-mono text-[10px] tabular-nums text-muted">
            기준 {String(data.as_of).replace('T', ' ').slice(0, 16)} · 2분 자동갱신
          </span>
        ) : undefined
      }
    >
      <div className="divide-y divide-line/60">
        {SECTIONS.map(s => {
          const rows = data[s.key] ?? []
          if (rows.length === 0) return null
          return (
            <div key={s.key}>
              {/* 섹션 헤더 */}
              <div className="flex items-center gap-2 bg-card-2/40 px-4 py-2">
                <span className="text-hanwha">{s.icon}</span>
                <span className="font-mono text-[11px] font-semibold uppercase tracking-[0.07em] text-muted">
                  {s.label}
                </span>
              </div>
              {/* 행 */}
              <table className="w-full border-collapse">
                <tbody>
                  {rows.map((r, i) => (
                    <tr
                      key={`${r.name}-${i}`}
                      className="border-b border-line/30 transition-colors last:border-b-0 hover:bg-card-2/30"
                    >
                      <td className="px-4 py-2 text-left font-sans text-xs text-greige whitespace-nowrap">
                        {r.name}
                      </td>
                      <td className="px-3 py-2 text-right text-xs tabular-nums">
                        <ValueDisplay v={r.value} unit={r.chg_unit} name={r.name} />
                      </td>
                      <td className="px-4 py-2 text-right text-xs whitespace-nowrap">
                        <ChgDisplay v={r.chg_1d} unit={r.chg_unit} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )
        })}
      </div>
    </Card>
  )
}
