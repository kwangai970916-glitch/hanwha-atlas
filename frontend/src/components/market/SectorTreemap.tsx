/**
 * SectorTreemap — Finviz 스타일 그룹 히트맵
 *
 * - /api/market/heatmap : GICS 11 대분류 그룹 + 대분류별 시총가중 등락률 + 대표 종목
 * - squarified treemap 2단: ① 대분류 블록(시총 비례) ② 블록 내 종목 타일(시총 비례)
 * - 색 = 등락률(한국 관례: 상승=레드 / 하락=블루), 크기 = 시총
 * - 종목 타일 호버 → 플로팅 패널: 등락률 · 현재가 · 시총 · 당일 일중 분봉 스파크라인
 * - 로딩 / 빈 / 에러 3종 상태
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { LayoutGrid } from 'lucide-react'
import { Card, Badge, Skeleton, EmptyState, ErrorState } from '../ui'
import { Sparkline } from '../ui/Sparkline'
import { squarify, type Rect } from './squarify'

/* ── 타입 ── */
type Stock = { code: string; name: string; change: number; market_cap: number; price?: number | null }
type Sector = { sector: string; change: number; market_cap: number; count: number; stocks: Stock[] }
type HeatmapResponse = { sectors?: Sector[]; up?: number; down?: number; as_of?: string; error?: string }
type Intraday = { code: string; points: { t: string; price: number }[]; prev_close?: number | null; last?: number | null; change_pct?: number | null; error?: string }
type LoadState = 'loading' | 'ready' | 'empty' | 'error'

/* ── 색/포맷 ── */
const CHG_CAP = 3 // ±3% 에서 색 포화

function tileBg(chg: number): string {
  if (Math.abs(chg) < 0.05) return 'rgba(140,140,150,0.16)'
  const r = Math.min(Math.abs(chg) / CHG_CAP, 1)
  const a = (0.16 + r * 0.64).toFixed(2)
  return chg > 0 ? `rgba(229,72,77,${a})` : `rgba(51,149,186,${a})`
}

function fmtCap(eok: number): string {
  // market_cap 단위 = 억원
  const jo = eok / 1e4
  if (jo >= 1) return `${jo.toLocaleString('ko-KR', { maximumFractionDigits: jo >= 100 ? 0 : 1 })}조`
  return `${Math.round(eok).toLocaleString('ko-KR')}억`
}

function fmtChange(chg: number): string {
  const sign = chg >= 0 ? '+' : '−'
  return `${sign}${Math.abs(chg).toFixed(2)}%`
}

/* ── 레이아웃 산출 ── */
const HEADER_H = 22

type Placed = { sector: Sector; rect: Rect; tiles: { stock: Stock; rect: Rect }[] }

function buildLayout(sectors: Sector[], w: number, h: number): Placed[] {
  if (w <= 0 || h <= 0) return []
  const sectorRects = squarify(
    sectors.map((s) => ({ value: Math.max(s.market_cap, 1), data: s })),
    { x: 0, y: 0, w, h },
  )
  return sectorRects.map(({ rect, data: sector }) => {
    const showHeader = rect.h > HEADER_H + 24 && rect.w > 60
    const inner: Rect = showHeader
      ? { x: rect.x, y: rect.y + HEADER_H, w: rect.w, h: rect.h - HEADER_H }
      : rect
    const tiles = squarify(
      sector.stocks.map((s) => ({ value: Math.max(s.market_cap, 1), data: s })),
      inner,
    ).map(({ rect: r, data: stock }) => ({ stock, rect: r }))
    return { sector, rect, tiles }
  })
}

/* ── 호버 플로팅 패널 ── */
function HoverPanel({ apiBase, stock, x, y }: { apiBase: string; stock: Stock; x: number; y: number }) {
  const [intra, setIntra] = useState<Intraday | null>(null)
  const [loading, setLoading] = useState(true)
  const cacheRef = useRef<Map<string, Intraday>>(new Map())

  useEffect(() => {
    let alive = true
    const cached = cacheRef.current.get(stock.code)
    if (cached) {
      setIntra(cached)
      setLoading(false)
      return
    }
    setLoading(true)
    fetch(`${apiBase}/api/market/intraday/${stock.code}?points=80`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: Intraday) => {
        if (!alive) return
        cacheRef.current.set(stock.code, d)
        setIntra(d)
        setLoading(false)
      })
      .catch(() => { if (alive) { setIntra(null); setLoading(false) } })
    return () => { alive = false }
  }, [apiBase, stock.code])

  const up = stock.change >= 0
  // 전일종가를 기준선으로 prepend → 하락 종목이 상승 모양으로 보이는 자동스케일 왜곡 방지
  const rawPoints = (intra?.points ?? []).map((p) => p.price)
  const prices = intra?.prev_close != null ? [intra.prev_close, ...rawPoints] : rawPoints
  // 색·등락률 모두 히트맵 타일과 동일 소스(stock.change)로 통일
  const sparkColor = stock.change >= 0 ? 'var(--up)' : 'var(--down)'

  // 화면 밖으로 넘어가지 않도록 clamp
  const PW = 232
  const left = Math.min(x + 16, (typeof window !== 'undefined' ? window.innerWidth : 1200) - PW - 12)
  const top = Math.max(12, y - 16)

  return (
    <div
      className="pointer-events-none fixed z-50 rounded-card border border-line bg-card/95 px-3 py-2.5 shadow-card backdrop-blur"
      style={{ left, top, width: PW }}
    >
      <div className="flex items-baseline justify-between gap-2">
        <span className="truncate text-sm font-semibold text-beige">{stock.name}</span>
        <span className="font-mono text-[10px] text-muted">{stock.code}</span>
      </div>
      <div className="mt-1 flex items-baseline justify-between">
        <span className={`font-mono text-lg font-bold tabular-nums ${up ? 'text-up' : 'text-down'}`}>
          {fmtChange(stock.change)}
        </span>
        {stock.price != null && (
          <span className="font-mono text-xs tabular-nums text-greige">
            {Math.round(stock.price).toLocaleString('ko-KR')}원
          </span>
        )}
      </div>

      <div className="mt-2 border-t border-line/50 pt-2">
        <div className="mb-1 flex items-center justify-between text-[10px] uppercase tracking-wide text-muted">
          <span>당일 일중 흐름</span>
          <span className={(up ? 'text-up' : 'text-down') + ' font-mono'}>
            {fmtChange(stock.change)}
          </span>
        </div>
        {loading ? (
          <Skeleton className="h-9 w-full rounded-chip" />
        ) : prices.length >= 2 ? (
          <Sparkline data={prices} color={sparkColor} width={PW - 24} height={38} />
        ) : (
          <p className="py-2 text-center text-[11px] text-muted">일중 데이터 없음</p>
        )}
      </div>

      <div className="mt-2 flex items-center justify-between text-[11px] text-muted">
        <span>시총</span>
        <span className="font-mono tabular-nums text-greige">{fmtCap(stock.market_cap)}</span>
      </div>
    </div>
  )
}

/* ── 메인 ── */
export function SectorTreemap({ apiBase }: { apiBase: string }) {
  const [state, setState] = useState<LoadState>('loading')
  const [sectors, setSectors] = useState<Sector[]>([])
  const [up, setUp] = useState(0)
  const [down, setDown] = useState(0)

  const wrapRef = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ w: 0, h: 560 })
  const [hover, setHover] = useState<{ stock: Stock; x: number; y: number } | null>(null)

  const load = useCallback((initial = false) => {
    if (initial) setState('loading')
    fetch(`${apiBase}/api/market/heatmap`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d: HeatmapResponse) => {
        if (d.error) throw new Error(d.error)
        const list = (d.sectors ?? []).filter((s) => s && s.stocks?.length && s.sector)
        setSectors(list)
        setUp(d.up ?? list.filter((s) => s.change >= 0).length)
        setDown(d.down ?? list.filter((s) => s.change < 0).length)
        setState(list.length > 0 ? 'ready' : 'empty')
      })
      .catch(() => setState((prev) => (prev === 'ready' ? 'ready' : 'error')))
  }, [apiBase])

  useEffect(() => {
    load(true)
    const id = setInterval(() => load(false), 300_000) // 5분 자동 갱신
    return () => clearInterval(id)
  }, [load])

  // 컨테이너 폭 측정(반응형)
  useEffect(() => {
    const el = wrapRef.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cr = entries[0]?.contentRect
      if (cr) setSize((s) => ({ ...s, w: Math.floor(cr.width) }))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [state])

  const layout = useMemo(() => buildLayout(sectors, size.w, size.h), [sectors, size.w, size.h])

  return (
    <Card
      eyebrow="Sector Map"
      title="시장 히트맵"
      action={
        state === 'ready' ? (
          <div className="flex items-center gap-2">
            <Badge tone="up">{up}↑</Badge>
            <Badge tone="down">{down}↓</Badge>
            <Badge tone="neutral">11 대분류</Badge>
          </div>
        ) : undefined
      }
    >
      {state === 'loading' && (
        <div className="grid grid-cols-4 gap-2" style={{ height: 560 }}>
          {Array.from({ length: 16 }).map((_, i) => (
            <Skeleton key={i} className={`w-full rounded-chip ${i < 2 ? 'h-40 col-span-2' : i < 6 ? 'h-32' : 'h-24'}`} />
          ))}
        </div>
      )}

      {state === 'error' && (
        <ErrorState
          title="히트맵 데이터를 불러오지 못했습니다"
          message="시장 히트맵 응답에 실패했습니다."
          onRetry={load}
          className="border-0 bg-transparent px-0 py-6"
        />
      )}

      {state === 'empty' && (
        <EmptyState
          icon={<LayoutGrid size={20} strokeWidth={1.75} />}
          title="히트맵 데이터 없음"
          description="표시할 종목 등락 데이터가 아직 없습니다."
          className="border-0 bg-transparent px-0 py-6"
        />
      )}

      {state === 'ready' && (
        <>
          <motion.div
            ref={wrapRef}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.4 }}
            className="relative w-full"
            style={{ height: size.h }}
            onMouseLeave={() => setHover(null)}
          >
            {layout.map(({ sector, rect, tiles }) => {
              const showHeader = rect.h > HEADER_H + 24 && rect.w > 60
              const sUp = sector.change >= 0
              return (
                <div key={sector.sector}>
                  {/* 대분류 블록 테두리 + 헤더 */}
                  <div
                    className="absolute rounded-[7px] border border-line/70"
                    style={{ left: rect.x, top: rect.y, width: rect.w, height: rect.h, pointerEvents: 'none' }}
                  />
                  {showHeader && (
                    <div
                      className="absolute flex items-center justify-between gap-1 px-1.5"
                      style={{ left: rect.x + 2, top: rect.y + 2, width: rect.w - 4, height: HEADER_H - 2, pointerEvents: 'none' }}
                    >
                      <span className="truncate text-[11px] font-semibold text-beige/90">{sector.sector}</span>
                      <span className={`shrink-0 font-mono text-[10px] tabular-nums ${sUp ? 'text-up' : 'text-down'}`}>
                        {fmtChange(sector.change)}
                      </span>
                    </div>
                  )}
                  {/* 종목 타일 */}
                  {tiles.map(({ stock, rect: tr }) => {
                    const showName = tr.w > 46 && tr.h > 30
                    const showChg = tr.w > 38 && tr.h > 22
                    const tUp = stock.change >= 0
                    return (
                      <div
                        key={stock.code}
                        className="absolute flex cursor-pointer flex-col items-center justify-center overflow-hidden rounded-[4px] transition-[filter] duration-150 hover:brightness-125"
                        style={{
                          left: tr.x + 1,
                          top: tr.y + 1,
                          width: Math.max(tr.w - 2, 0),
                          height: Math.max(tr.h - 2, 0),
                          background: tileBg(stock.change),
                          boxShadow: 'inset 0 0 0 0.5px rgba(0,0,0,0.25)',
                        }}
                        onMouseEnter={(e) => setHover({ stock, x: e.clientX, y: e.clientY })}
                        onMouseMove={(e) => setHover({ stock, x: e.clientX, y: e.clientY })}
                        onClick={() => stock.code && window.dispatchEvent(new CustomEvent('market:select-symbol', { detail: { code: stock.code, name: stock.name } }))}
                      >
                        {showName && (
                          <span
                            className="px-0.5 text-center font-medium leading-tight text-beige"
                            style={{ fontSize: Math.min(11, Math.max(8, tr.w / 9)), pointerEvents: 'none' }}
                          >
                            {stock.name.length > 7 ? stock.name.slice(0, 6) + '…' : stock.name}
                          </span>
                        )}
                        {showChg && (
                          <span
                            className={`font-mono font-bold tabular-nums ${tUp ? 'text-up' : 'text-down'}`}
                            style={{ fontSize: Math.min(12, Math.max(8, tr.w / 8)), pointerEvents: 'none' }}
                          >
                            {fmtChange(stock.change)}
                          </span>
                        )}
                      </div>
                    )
                  })}
                </div>
              )
            })}
          </motion.div>
          {hover && <HoverPanel apiBase={apiBase} stock={hover.stock} x={hover.x} y={hover.y} />}
          <p className="mt-2 text-[10px] text-muted">
            크기 = 시가총액 · 색 = 등락률(상승 레드 / 하락 블루) · 종목 호버 시 일중 흐름·시총 표시 · 미분류 종목 제외
          </p>
        </>
      )}
    </Card>
  )
}

export default SectorTreemap
