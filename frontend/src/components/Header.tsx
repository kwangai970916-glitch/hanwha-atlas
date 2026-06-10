import { useEffect, useMemo, useState } from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { AlertTriangle, RotateCw, WifiOff } from 'lucide-react'
import { Badge } from './ui'
import { cn } from '../lib/utils'

type Tick = {
  symbol: string
  display?: string
  /** 현재가 (백엔드 price). 구버전 value 도 허용 */
  price?: number
  value?: number
  change: number
  asset_type?: string
  sector?: string
}

type HeaderProps = {
  /** 라이브 마켓 테이프 데이터 */
  ticks: Tick[]
  /** 최초 스트림 연결 전 로딩 표시 (선택) */
  loading?: boolean
  /** 스트림 에러 메시지 (선택) — 있으면 에러 상태 노출 */
  error?: string | null
  /** 에러 재시도 핸들러 (선택) */
  onRetry?: () => void
  /** 데이터 기준시각 as_of (선택, ISO8601) */
  asOf?: string
}

/** 한화 로고 모티프 — 오렌지 동심원 링 (라이브 펄스용 미니 마크) */
function LiveRing({ active }: { active: boolean }) {
  return (
    <span className="relative grid h-3.5 w-3.5 shrink-0 place-items-center">
      {active && (
        <span className="absolute inset-0 animate-pulse-soft rounded-full bg-hanwha/25" />
      )}
      <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden>
        <circle
          cx="8"
          cy="8"
          r="6.5"
          fill="none"
          stroke="var(--hanwha)"
          strokeOpacity={active ? 0.4 : 0.18}
          strokeWidth="1.5"
        />
        <circle cx="8" cy="8" r="2.4" fill={active ? 'var(--hanwha)' : 'var(--muted)'} />
      </svg>
    </span>
  )
}

/** 한 종목 셀 — 티커 / 현재가 / 등락(한국 관례색) */
function TickCell({ tick }: { tick: Tick }) {
  const px = tick.price ?? tick.value ?? 0
  const pos = tick.change >= 0
  return (
    <span className="flex items-center gap-1.5 font-mono text-xs tabular-nums">
      <span className="text-greige">{tick.display ?? tick.symbol}</span>
      <span className="text-beige">
        {px.toLocaleString('ko-KR', { maximumFractionDigits: 2 })}
      </span>
      <span className={cn('inline-flex items-center gap-0.5 font-semibold', pos ? 'text-up' : 'text-down')}>
        <span className="text-[0.85em] leading-none">{pos ? '▲' : '▼'}</span>
        {Math.abs(tick.change).toFixed(2)}%
      </span>
      <span aria-hidden className="text-line">·</span>
    </span>
  )
}

/**
 * KST(UTC+9) 기준 한국 정규장 세션 판정.
 * 정규장: 평일(월~금) 09:00 ~ 15:30. 그 외엔 장마감/휴장.
 * 클라이언트 로컬 타임존과 무관하게 UTC 로부터 KST 를 직접 환산한다.
 */
function getKstSession(now: Date): { open: boolean; label: string } {
  const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000)
  const day = kst.getUTCDay() // 0=일 … 6=토
  const minutes = kst.getUTCHours() * 60 + kst.getUTCMinutes()
  const weekday = day >= 1 && day <= 5
  const open = weekday && minutes >= 9 * 60 && minutes <= 15 * 60 + 30
  if (!weekday) return { open: false, label: '휴장' }
  return { open, label: open ? '장중' : '장마감' }
}

/** as_of ISO 문자열을 HH:MM:SS (KST) 로 포맷. 실패시 null */
function formatAsOf(asOf?: string): string | null {
  if (!asOf) return null
  const d = new Date(asOf)
  if (Number.isNaN(d.getTime())) return null
  return d.toLocaleTimeString('ko-KR', { hour12: false })
}

/**
 * 라이브 마켓 테이프 — 브랜드바 아래 스트립.
 * - 한화 오렌지 동심원 링 + LIVE 펄스 + 장중/장마감 세션 pill + as-of 시계.
 * - ticks 를 한국 관례색(상승=레드, 하락=블루)으로 끊김없이 흐르게 표시.
 * - 비동기 3종: 로딩(스켈레톤) · 빈 상태(연결 대기) · 에러 상태(재시도).
 * - 숫자/티커는 Pretendard/Noto Sans KR(tabular-nums).
 */
export function Header({ ticks, loading = false, error = null, onRetry, asOf }: HeaderProps) {
  const reduce = useReducedMotion()
  const [now, setNow] = useState(() => new Date())
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000)
    return () => clearInterval(t)
  }, [])

  const session = useMemo(() => getKstSession(now), [now])
  const live = ticks.length > 0 && !error
  const clock = now.toLocaleTimeString('ko-KR', { hour12: false })
  const asOfClock = formatAsOf(asOf)

  // 끊김없는 마퀴를 위해 트랙을 2배 복제 (reduced-motion 이면 정적)
  const marqueeDuration = Math.max(28, ticks.length * 3.2)

  return (
    <div className="flex h-9 items-center gap-3 border-t border-line bg-card-2/40 px-6 backdrop-blur">
      {/* 좌측: 라이브 링 + 세션 상태 */}
      <div className="flex shrink-0 items-center gap-2">
        <LiveRing active={live && session.open} />
        <span
          className={cn(
            'font-mono text-[11px] font-semibold uppercase tracking-[0.1em]',
            live ? 'text-hanwha' : 'text-muted',
          )}
        >
          {live ? 'LIVE' : 'IDLE'}
        </span>
        <Badge tone={session.open ? 'up' : 'neutral'} dot className="hidden sm:inline-flex">
          {session.label}
        </Badge>
      </div>

      <span aria-hidden className="hidden h-3.5 w-px shrink-0 bg-line sm:block" />

      {/* 중앙: 흐르는 테이프 / 비동기 상태 */}
      <div className="relative min-w-0 flex-1 overflow-hidden">
        {loading ? (
          // (1) 로딩 스켈레톤
          <div className="flex items-center gap-6">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex shrink-0 items-center gap-2">
                <span className="h-3 w-9 animate-pulse rounded-chip bg-card-2/70" />
                <span className="h-3 w-14 animate-pulse rounded-chip bg-card-2/70" />
                <span className="h-3 w-10 animate-pulse rounded-chip bg-card-2/70" />
              </div>
            ))}
          </div>
        ) : error ? (
          // (3) 에러 상태
          <div className="flex items-center gap-2 font-mono text-xs">
            <AlertTriangle size={13} className="shrink-0 text-up" strokeWidth={2} />
            <span className="truncate text-up">{error || '시세 스트림 오류'}</span>
            {onRetry && (
              <button
                onClick={onRetry}
                className="ml-1 inline-flex shrink-0 items-center gap-1 rounded-chip border border-line bg-card-2 px-2 py-0.5 text-[11px] font-semibold text-beige transition-colors hover:border-hanwha hover:text-hanwha"
              >
                <RotateCw size={11} strokeWidth={2.2} />
                재시도
              </button>
            )}
          </div>
        ) : !live ? (
          // (2) 빈 상태
          <span className="inline-flex items-center gap-2 font-mono text-xs text-muted">
            <WifiOff size={13} className="shrink-0" strokeWidth={2} />
            시세 스트림 연결 대기 중…
          </span>
        ) : (
          // 정상: 마퀴 테이프
          <div className="flex w-max">
            <span className="sr-only">실시간 시세 마퀴</span>
            <motion.div
              aria-hidden
              className="flex shrink-0 items-center gap-6 pr-6"
              animate={reduce ? undefined : { x: ['0%', '-100%'] }}
              transition={
                reduce
                  ? undefined
                  : { duration: marqueeDuration, ease: 'linear', repeat: Infinity }
              }
            >
              {ticks.map((t, i) => (
                <TickCell key={`a-${t.symbol}-${i}`} tick={t} />
              ))}
            </motion.div>
            {!reduce && (
              <motion.div
                aria-hidden
                className="flex shrink-0 items-center gap-6 pr-6"
                animate={{ x: ['0%', '-100%'] }}
                transition={{ duration: marqueeDuration, ease: 'linear', repeat: Infinity }}
              >
                {ticks.map((t, i) => (
                  <TickCell key={`b-${t.symbol}-${i}`} tick={t} />
                ))}
              </motion.div>
            )}
            {/* 양끝 페이드 마스크 */}
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 left-0 w-8 bg-gradient-to-r from-card-2/40 to-transparent"
            />
            <span
              aria-hidden
              className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-card-2/40 to-transparent"
            />
          </div>
        )}
      </div>

      {/* 우측: as-of + 실시간 시계 */}
      <div className="flex shrink-0 items-center gap-2 font-mono tabular-nums">
        {asOfClock && (
          <span className="hidden text-[11px] text-muted md:inline">
            기준 {asOfClock}
          </span>
        )}
        <span className="text-[11px] text-greige">KST</span>
        <span className="text-[11px] text-beige">{clock}</span>
      </div>
    </div>
  )
}

export default Header
