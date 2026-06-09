/**
 * MetricCard — 3D 입체 KPI 카드 프리미엄 컴포넌트
 *
 * 기법:
 * 1. 글래스모픽 서피스: bg-card/70 + backdrop-blur + 웜 radial inner gradient
 * 2. 그라데이션/글로우 보더: wrapper gradient-padding ring
 * 3. 레이어드 드롭 쉐도우: 카드가 캔버스에서 떠오르는 느낌
 * 4. 3D 포인터 틸트: useMotionValue + useTransform → rotateX/Y ±6deg + perspective
 * 5. 숫자 카운트업: useEffect interpolation, tabular-nums 지터 없음
 * 6. 변화 pill: 한국 관례색(상승=레드, 하락=블루) + bg-up/10 bg-down/10 배경
 * 7. KOSPI(primary) 카드 강화 오렌지 글로우 옵션
 */

import { useEffect, useRef, useState } from 'react'
import {
  motion,
  useMotionValue,
  useSpring,
  useTransform,
} from 'framer-motion'
import { cn } from '../../lib/utils'

/* ─────────────────────────────────────────────
   숫자 카운트업 훅
   ───────────────────────────────────────────── */
function useCountUp(target: number | null, duration = 900): number | null {
  const [current, setCurrent] = useState<number | null>(target)
  const prevRef = useRef<number | null>(null)
  const rafRef = useRef<number | null>(null)

  useEffect(() => {
    if (target === null) {
      setCurrent(null)
      prevRef.current = null
      return
    }

    const start = prevRef.current ?? target
    const startTime = performance.now()

    const step = (now: number) => {
      const elapsed = now - startTime
      const progress = Math.min(elapsed / duration, 1)
      // easeOutCubic
      const eased = 1 - Math.pow(1 - progress, 3)
      const value = start + (target - start) * eased
      setCurrent(value)
      if (progress < 1) {
        rafRef.current = requestAnimationFrame(step)
      } else {
        prevRef.current = target
      }
    }

    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    rafRef.current = requestAnimationFrame(step)

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current)
    }
  }, [target, duration])

  return current
}

/* ─────────────────────────────────────────────
   카드 타입
   ───────────────────────────────────────────── */
export type MetricCardProps = {
  label: string
  value: number | null
  change: number | null
  suffix?: string
  digits?: number
  /** 지수용 포인트 변화(±pt). 지정 시 % pill 옆에 함께 표기 */
  changePt?: number | null
  /** KOSPI 등 1순위 — 강한 오렌지 글로우 */
  primary?: boolean
  className?: string
}

/* ─────────────────────────────────────────────
   MetricCard
   ───────────────────────────────────────────── */
export function MetricCard({
  label,
  value,
  change,
  suffix,
  digits = 2,
  changePt,
  primary = false,
  className,
}: MetricCardProps) {
  const cardRef = useRef<HTMLDivElement>(null)

  /* 3D 틸트 — spring 부드럽게 */
  const rawX = useMotionValue(0)
  const rawY = useMotionValue(0)
  const springConfig = { stiffness: 220, damping: 28, mass: 0.6 }
  const springX = useSpring(rawX, springConfig)
  const springY = useSpring(rawY, springConfig)

  const rotateX = useTransform(springY, [-0.5, 0.5], [6, -6])
  const rotateY = useTransform(springX, [-0.5, 0.5], [-6, 6])
  const glowOpacity = useTransform(
    springX,
    [-0.5, 0, 0.5],
    [0.18, primary ? 0.32 : 0.08, 0.18],
  )

  function handleMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    const rect = cardRef.current?.getBoundingClientRect()
    if (!rect) return
    const x = (e.clientX - rect.left) / rect.width - 0.5
    const y = (e.clientY - rect.top) / rect.height - 0.5
    rawX.set(x)
    rawY.set(y)
  }

  function handleMouseLeave() {
    rawX.set(0)
    rawY.set(0)
  }

  /* 카운트업 */
  const animatedValue = useCountUp(value)

  /* 포맷 */
  function fmt(v: number | null): string {
    if (v === null || Number.isNaN(v)) return '—'
    return v.toLocaleString('ko-KR', {
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
  }

  const isNull = value === null
  const pos = typeof change === 'number' ? change >= 0 : null

  /* 보더 그라데이션 래퍼 색상 */
  const borderGradient = primary
    ? 'bg-gradient-to-br from-hanwha/60 via-line/60 to-line/30'
    : 'bg-gradient-to-br from-line/80 via-line/40 to-line/10'

  return (
    /* 그라데이션 보더 래퍼 — 1px padding으로 보더 효과 */
    <div
      className={cn(
        'rounded-card p-px transition-all duration-300',
        borderGradient,
        primary && 'shadow-glow',
        className,
      )}
      style={{ perspective: '800px' }}
    >
      <motion.div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        style={{
          rotateX,
          rotateY,
          transformStyle: 'preserve-3d',
        }}
        whileHover={{ scale: 1.025 }}
        transition={{ type: 'spring', stiffness: 260, damping: 26 }}
        className={cn(
          /* 글래스모픽 서피스 */
          'relative flex flex-col gap-2.5 overflow-hidden rounded-[17px]',
          'border border-white/[0.04]',
          'bg-card/80 backdrop-blur-md',
          /* 레이어드 쉐도우 */
          'shadow-card',
          'cursor-default select-none',
          'p-4',
        )}
      >
        {/* 상단 하이라이트 엣지 — inset 흰빛 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 top-0 h-px rounded-t-[17px] bg-gradient-to-r from-transparent via-white/10 to-transparent"
        />

        {/* 웜 내부 radial 그라데이션 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[17px]"
          style={{
            background:
              'radial-gradient(ellipse at 30% 0%, rgba(243,115,33,0.07) 0%, transparent 60%)',
          }}
        />

        {/* 포인터 추적 스포트라이트 글로우 */}
        <motion.div
          aria-hidden
          className="pointer-events-none absolute inset-0 rounded-[17px]"
          style={{
            opacity: glowOpacity,
            background: primary
              ? 'radial-gradient(circle at 50% 0%, rgba(243,115,33,0.30), transparent 70%)'
              : 'radial-gradient(circle at 50% 0%, rgba(90,74,67,0.60), transparent 70%)',
          }}
        />

        {/* ── 라벨 칩 ── */}
        <div className="relative flex items-center justify-between">
          <span
            className={cn(
              'font-mono text-[10px] font-semibold uppercase tracking-[0.10em]',
              primary ? 'text-hanwha-2' : 'text-muted',
            )}
          >
            {label}
          </span>
          {/* 프라이머리 전용 라이브 점 */}
          {primary && (
            <span
              aria-label="실시간"
              className="block h-1.5 w-1.5 animate-pulse-soft rounded-full bg-hanwha"
            />
          )}
        </div>

        {/* ── 메인 수치 ── */}
        <div className="relative flex items-baseline gap-1">
          {/* $ 기호는 숫자 앞에 */}
          {!isNull && suffix === '$' && (
            <span className="font-mono text-sm font-semibold text-muted">$</span>
          )}
          <span
            className={cn(
              'font-mono text-2xl font-bold tabular-nums leading-none',
              isNull ? 'text-muted' : 'text-beige',
            )}
          >
            {fmt(animatedValue)}
          </span>
          {/* $ 외 단위(원 등)는 숫자 뒤에 */}
          {!isNull && suffix && suffix !== '$' && (
            <span className="font-mono text-sm font-semibold text-muted">{suffix}</span>
          )}
        </div>

        {/* ── 변화 pill ── */}
        <div className="relative">
          {typeof change === 'number' ? (
            <span
              className={cn(
                'inline-flex items-center gap-1 rounded-pill font-mono text-[11px] font-semibold tabular-nums',
                'px-1.5 py-0.5',
                pos
                  ? 'bg-up/10 text-up'
                  : 'bg-down/10 text-down',
              )}
            >
              <span className="text-[0.85em] leading-none">{pos ? '▲' : '▼'}</span>
              {typeof changePt === 'number' && (
                <span className="tabular-nums">{pos ? '+' : '-'}{Math.abs(changePt).toLocaleString('ko-KR', { maximumFractionDigits: 2 })}</span>
              )}
              <span className="opacity-90">{pos ? '+' : '-'}{Math.abs(change).toFixed(2)}%</span>
            </span>
          ) : (
            <span className="font-mono text-[11px] text-muted">—</span>
          )}
        </div>

        {/* 바닥 그라데이션 페이드 */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-x-0 bottom-0 h-8 rounded-b-[17px]"
          style={{
            background:
              'linear-gradient(to top, rgba(58,47,44,0.40), transparent)',
          }}
        />
      </motion.div>
    </div>
  )
}

export default MetricCard
