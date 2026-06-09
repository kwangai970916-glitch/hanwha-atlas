/**
 * MarketRadar — 시장 폭 + 지수 견인 종목
 *
 * 시장 폭(Breadth):
 *   /api/market/universe?direction=up|down|all&limit=1 의 total로 상승/하락/보합 산출
 *   diverging 수평 막대 (상승=레드, 하락=블루, 보합=greige)
 *
 * 지수 견인 TOP:
 *   sort=contribution&order=desc&limit=6 (끌어올린)
 *   sort=contribution&order=asc&limit=6  (끌어내린)
 *   종목명 · 기여도(±pt) · 등락% 리스트
 */
import { useCallback, useEffect, useState } from 'react'
import { motion } from 'framer-motion'
import { TrendingUp, TrendingDown, Activity } from 'lucide-react'
import { Card, ChangePill, Skeleton, EmptyState, ErrorState } from '../ui'

/* ── 타입 ── */
type LoadState = 'loading' | 'ready' | 'empty' | 'error'

interface BreadthData {
  up: number
  down: number
  flat: number
  total: number
}

type Driver = { name: string; code: string; change?: number; contribution?: number }
type BreadthResponse = {
  up?: number; down?: number; flat?: number; total?: number
  advance_decline_ratio?: number | null
  top_drivers?: Driver[]; bottom_drivers?: Driver[]
  error?: string
}

/* ── 숫자 포맷 ── */
function fmtPt(v: number | undefined): string {
  if (v === undefined || v === null) return '—'
  const sign = v >= 0 ? '+' : ''
  const a = Math.abs(v)
  // 큰 값일수록 소수 자릿수를 줄여 폭을 절약(종목명 잘림 방지)
  const digits = a >= 100 ? 0 : a >= 10 ? 1 : 2
  return `${sign}${v.toFixed(digits)}pt`
}

/* ── 폭 막대 세그먼트 ── */
function BreadthBar({ breadth }: { breadth: BreadthData }) {
  const { up, down, flat, total } = breadth
  if (total === 0) return null

  const upPct = (up / total) * 100
  const downPct = (down / total) * 100
  const flatPct = (flat / total) * 100

  return (
    <div className="space-y-3">
      {/* 막대 */}
      <div className="flex h-5 w-full overflow-hidden rounded-pill">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${upPct}%` }}
          transition={{ duration: 0.7, ease: 'easeOut' }}
          className="h-full bg-up/75"
          title={`상승 ${up}종목`}
        />
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${flatPct}%` }}
          transition={{ duration: 0.7, delay: 0.1, ease: 'easeOut' }}
          className="h-full bg-greige/20"
          title={`보합 ${flat}종목`}
        />
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${downPct}%` }}
          transition={{ duration: 0.7, delay: 0.2, ease: 'easeOut' }}
          className="h-full bg-down/65"
          title={`하락 ${down}종목`}
        />
      </div>

      {/* 레전드 */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-chip bg-up/10 border border-up/20 px-2 py-2">
          <p className="font-mono text-lg font-bold tabular-nums text-up leading-none">{up}</p>
          <p className="mt-1 text-[10px] font-semibold text-muted uppercase tracking-wide">상승</p>
          <p className="font-mono text-[10px] text-muted tabular-nums">{upPct.toFixed(1)}%</p>
        </div>
        <div className="rounded-chip bg-card-2/50 border border-line px-2 py-2">
          <p className="font-mono text-lg font-bold tabular-nums text-greige leading-none">{flat}</p>
          <p className="mt-1 text-[10px] font-semibold text-muted uppercase tracking-wide">보합</p>
          <p className="font-mono text-[10px] text-muted tabular-nums">{flatPct.toFixed(1)}%</p>
        </div>
        <div className="rounded-chip bg-down/10 border border-down/20 px-2 py-2">
          <p className="font-mono text-lg font-bold tabular-nums text-down leading-none">{down}</p>
          <p className="mt-1 text-[10px] font-semibold text-muted uppercase tracking-wide">하락</p>
          <p className="font-mono text-[10px] text-muted tabular-nums">{downPct.toFixed(1)}%</p>
        </div>
      </div>
    </div>
  )
}

/* ── 지수 견인 종목 리스트 행 ── */
function DriverRow({
  stock,
  rank,
  direction,
}: {
  stock: Driver
  rank: number
  direction: 'up' | 'down'
}) {
  const pt = stock.contribution ?? 0
  const change = stock.change ?? 0
  const isUp = direction === 'up'

  return (
    <motion.div
      initial={{ opacity: 0, x: isUp ? -8 : 8 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ delay: rank * 0.06, type: 'spring', stiffness: 280, damping: 26 }}
      className="flex items-center gap-2.5 py-1.5 border-b border-line/30 last:border-0 cursor-pointer hover:bg-card-2/40 rounded px-1 -mx-1"
      onClick={() => stock.code && window.dispatchEvent(new CustomEvent('market:select-symbol', { detail: { code: stock.code, name: stock.name } }))}
    >
      {/* 랭크 */}
      <span className="font-mono text-[10px] text-muted tabular-nums w-4 text-right shrink-0">
        {rank + 1}
      </span>

      {/* 종목명 */}
      <span className="flex-1 truncate text-xs font-semibold text-beige min-w-0">
        {stock.name}
      </span>

      {/* 기여도 */}
      <span
        className={`font-mono text-xs font-bold tabular-nums shrink-0 ${isUp ? 'text-up' : 'text-down'}`}
      >
        {fmtPt(pt)}
      </span>

      {/* 등락 pill */}
      <ChangePill value={change} size="sm" />
    </motion.div>
  )
}

/* ── 메인 컴포넌트 ── */
export function MarketRadar({ apiBase }: { apiBase: string }) {
  const [breadthState, setBreadthState] = useState<LoadState>('loading')
  const [breadth, setBreadth] = useState<BreadthData | null>(null)
  const [topDrivers, setTopDrivers] = useState<Driver[]>([])
  const [bottomDrivers, setBottomDrivers] = useState<Driver[]>([])

  /* ── 시장 폭 + 견인 종목 단일 로드 (/api/market/breadth) ── */
  const load = useCallback((initial = false) => {
    if (initial) setBreadthState('loading')
    fetch(`${apiBase}/api/market/breadth`)
      .then(r => (r.ok ? (r.json() as Promise<BreadthResponse>) : Promise.reject(new Error('http'))))
      .then(d => {
        if (d.error) throw new Error(d.error)
        const total = d.total ?? 0
        if (total === 0) { setBreadthState('empty'); return }
        setBreadth({ up: d.up ?? 0, down: d.down ?? 0, flat: d.flat ?? 0, total })
        setTopDrivers(d.top_drivers ?? [])
        setBottomDrivers(d.bottom_drivers ?? [])
        setBreadthState('ready')
      })
      .catch(() => setBreadthState(prev => (prev === 'ready' ? 'ready' : 'error'))) // 실패해도 직전 데이터 유지
  }, [apiBase])

  useEffect(() => {
    load(true)
    const id = setInterval(() => load(false), 60_000) // 60초 자동 갱신
    return () => clearInterval(id)
  }, [load])

  const isLoading = breadthState === 'loading'
  const driversState: LoadState = breadthState
  const loadBreadth = () => load(true)
  const loadDrivers = () => load(true)

  return (
    <Card eyebrow="Market Radar" title="시장 폭 · 지수 견인">
      {isLoading && (
        <div className="space-y-4">
          <Skeleton className="h-5 w-full rounded-pill" />
          <div className="grid grid-cols-3 gap-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} className="h-16 rounded-chip" />
            ))}
          </div>
          <div className="space-y-2 mt-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-7 w-full" />
            ))}
          </div>
        </div>
      )}

      {!isLoading && (breadthState === 'error' || driversState === 'error') && (
        <ErrorState
          title="시장 레이더 로드 실패"
          message="시장 폭 또는 견인 종목 데이터를 불러오지 못했습니다."
          onRetry={() => { loadBreadth(); loadDrivers() }}
          className="border-0 bg-transparent px-0 py-6"
        />
      )}

      {!isLoading && breadthState !== 'error' && driversState !== 'error' && (
        <div className="space-y-5">
          {/* ── 시장 폭 ── */}
          <div>
            <p className="mb-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.10em] text-hanwha flex items-center gap-2">
              <Activity size={11} />
              시장 폭 — KOSPI 전종목
            </p>
            {breadthState === 'empty' || !breadth ? (
              <EmptyState
                title="시장 폭 데이터 없음"
                description="장 시작 후 다시 확인해 주세요."
                className="border-0 bg-transparent py-4"
              />
            ) : (
              <BreadthBar breadth={breadth} />
            )}
          </div>

          {/* ── 구분선 ── */}
          <div className="h-px bg-line/60" />

          {/* ── 지수 견인 ── */}
          <div>
            <p className="mb-2.5 font-mono text-[10px] font-semibold uppercase tracking-[0.10em] text-hanwha">
              오늘 KOSPI를 움직인 종목
            </p>

            {driversState === 'empty' ? (
              <EmptyState
                title="견인 종목 데이터 없음"
                description="기여도 데이터가 아직 없습니다."
                className="border-0 bg-transparent py-4"
              />
            ) : (
              <div className="space-y-4">
                {/* 끌어올린 종목 */}
                <div>
                  <div className="flex items-center gap-1.5 mb-2">
                    <TrendingUp size={12} className="text-up shrink-0" />
                    <span className="text-[10px] font-semibold text-up uppercase tracking-wide">
                      견인 상위
                    </span>
                  </div>
                  {topDrivers.length === 0 ? (
                    <p className="text-xs text-muted py-2">데이터 없음</p>
                  ) : (
                    topDrivers.map((s, i) => (
                      <DriverRow key={s.code} stock={s} rank={i} direction="up" />
                    ))
                  )}
                </div>

                {/* 끌어내린 종목 */}
                <div className="mt-4 md:mt-0">
                  <div className="flex items-center gap-1.5 mb-2">
                    <TrendingDown size={12} className="text-down shrink-0" />
                    <span className="text-[10px] font-semibold text-down uppercase tracking-wide">
                      하방 압력
                    </span>
                  </div>
                  {bottomDrivers.length === 0 ? (
                    <p className="text-xs text-muted py-2">데이터 없음</p>
                  ) : (
                    bottomDrivers.map((s, i) => (
                      <DriverRow key={s.code} stock={s} rank={i} direction="down" />
                    ))
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </Card>
  )
}

export default MarketRadar
