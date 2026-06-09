import { cn } from '../../lib/utils'

type ChangePillProps = {
  /** 등락 값 (퍼센트 또는 절대값). 0 이상이면 상승(레드), 미만이면 하락(블루) */
  value: number
  /** % 접미사 표시 여부 (기본 true) */
  percent?: boolean
  /** 소수 자릿수 (기본 2) */
  digits?: number
  /** 화살표 표시 (기본 true) */
  arrow?: boolean
  size?: 'sm' | 'md'
  className?: string
}

/**
 * 등락 pill — 한국 관례색(상승=up 레드, 하락=down 블루) + 방향 화살표.
 * 오렌지(브랜드색)는 신호색으로 쓰지 않는다.
 */
export function ChangePill({
  value,
  percent = true,
  digits = 2,
  arrow = true,
  size = 'md',
  className,
}: ChangePillProps) {
  const pos = value >= 0
  const sign = pos ? '+' : '-'
  const glyph = pos ? '▲' : '▼'
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-pill font-mono font-semibold tabular-nums',
        size === 'sm' ? 'px-1.5 py-0.5 text-[11px]' : 'px-2 py-0.5 text-xs',
        pos
          ? 'bg-up/10 text-up'
          : 'bg-down/10 text-down',
        className,
      )}
    >
      {arrow && <span className="text-[0.85em] leading-none">{glyph}</span>}
      {sign}
      {Math.abs(value).toFixed(digits)}
      {percent && '%'}
    </span>
  )
}

export default ChangePill
