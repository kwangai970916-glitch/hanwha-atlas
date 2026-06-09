import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type Tone = 'neutral' | 'hanwha' | 'blue' | 'purple' | 'up' | 'down'

type BadgeProps = {
  children: ReactNode
  tone?: Tone
  /** 좌측 점 표시 (상태 인디케이터) */
  dot?: boolean
  className?: string
}

const TONES: Record<Tone, string> = {
  neutral: 'bg-card-2 text-greige border-line',
  hanwha: 'bg-hanwha/12 text-hanwha border-hanwha/25',
  blue: 'bg-blue/12 text-blue border-blue/25',
  purple: 'bg-purple/15 text-purple border-purple/30',
  up: 'bg-up/10 text-up border-up/25',
  down: 'bg-down/10 text-down border-down/25',
}

const DOT: Record<Tone, string> = {
  neutral: 'bg-greige',
  hanwha: 'bg-hanwha',
  blue: 'bg-blue',
  purple: 'bg-purple',
  up: 'bg-up',
  down: 'bg-down',
}

/** 작은 라벨/태그 칩. tone 으로 브랜드 토큰 색 지정. */
export function Badge({ children, tone = 'neutral', dot, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5',
        'font-mono text-[11px] font-semibold uppercase tracking-[0.04em]',
        TONES[tone],
        className,
      )}
    >
      {dot && <span className={cn('h-1.5 w-1.5 rounded-full', DOT[tone])} />}
      {children}
    </span>
  )
}

export default Badge
