/**
 * Stat (= Kpi) — 공유 KPI 프리미티브
 *
 * prop API는 하위호환 유지:
 *   label, value, delta?, deltaPercent?, hint?, className?
 *
 * 비주얼: 글래스모픽 서피스 + 상단 하이라이트 엣지 + 레이어드 쉐도우.
 * hover 시 y:-2 마이크로 리프트.
 * 숫자 = Pretendard/Noto Sans KR + tabular-nums.
 * 등락색 = 한국 관례 (상승=up 레드, 하락=down 블루).
 */

import type { ReactNode } from 'react'
import { motion } from 'framer-motion'
import { cn } from '../../lib/utils'
import { ChangePill } from './ChangePill'

type StatProps = {
  label: ReactNode
  /** 큰 수치 (이미 포맷된 문자열 또는 노드) */
  value: ReactNode
  /** 델타값 — 숫자면 ChangePill 로 렌더 (한국 관례색) */
  delta?: number
  /** 델타 단위가 % 인지 (기본 true) */
  deltaPercent?: boolean
  /** 보조 설명 텍스트 */
  hint?: ReactNode
  className?: string
}

/**
 * KPI 스탯 — 라벨 + 큰 수치 + 델타(up/down 색).
 * 수치는 Pretendard/Noto Sans KR + tabular-nums.
 */
export function Stat({
  label,
  value,
  delta,
  deltaPercent = true,
  hint,
  className,
}: StatProps) {
  return (
    <motion.div
      whileHover={{ y: -2, scale: 1.01 }}
      transition={{ type: 'spring', stiffness: 280, damping: 24 }}
      className={cn(
        /* 글래스모픽 서피스 */
        'relative flex flex-col gap-2 overflow-hidden rounded-card',
        'border border-white/[0.04]',
        'bg-card/80 backdrop-blur-md',
        /* 그라데이션 보더 효과를 위해 ring 활용 */
        'ring-1 ring-line/60',
        /* 레이어드 쉐도우 */
        'shadow-card',
        'p-4',
        className,
      )}
    >
      {/* 상단 하이라이트 엣지 */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-px rounded-t-card bg-gradient-to-r from-transparent via-white/10 to-transparent"
      />
      {/* 웜 inner radial */}
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 rounded-card"
        style={{
          background:
            'radial-gradient(ellipse at 30% 0%, rgba(243,115,33,0.05) 0%, transparent 55%)',
        }}
      />

      {/* 라벨 */}
      <span className="relative font-mono text-[11px] font-semibold uppercase tracking-[0.06em] text-muted">
        {label}
      </span>

      {/* 수치 */}
      <span className="relative font-mono text-2xl font-bold tabular-nums leading-none text-beige">
        {value}
      </span>

      {/* 델타 + hint */}
      <div className="relative flex items-center gap-2">
        {typeof delta === 'number' && (
          <ChangePill value={delta} percent={deltaPercent} size="sm" />
        )}
        {hint && <span className="text-[11px] text-muted">{hint}</span>}
      </div>
    </motion.div>
  )
}

/** Kpi 는 Stat 의 alias (요구 명세 양쪽 표기 대응) */
export const Kpi = Stat

export default Stat
