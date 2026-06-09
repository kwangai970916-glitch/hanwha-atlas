import { useId } from 'react'
import { cn } from '../../lib/utils'

type SparklineProps = {
  /** 데이터 포인트 배열 */
  data: number[]
  width?: number
  height?: number
  /** 선/영역 색 (CSS 색값 또는 var()). 미지정시 등락 방향 기준 자동(up/down) */
  color?: string
  /** 영역(그라데이션 fill) 표시 (기본 true) */
  area?: boolean
  strokeWidth?: number
  className?: string
}

/**
 * 순수 SVG 스파크라인. 데이터 배열을 받아 라인 + (옵션)영역 렌더.
 * 색 미지정시 마지막 >= 첫값이면 up(레드), 아니면 down(블루).
 * 새 패키지 설치 없이 동작.
 */
export function Sparkline({
  data,
  width = 120,
  height = 36,
  color,
  area = true,
  strokeWidth = 1.75,
  className,
}: SparklineProps) {
  const gradId = useId()

  if (!data || data.length < 2) {
    return (
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className={cn('block', className)}
        aria-hidden
      >
        <line
          x1={0}
          y1={height / 2}
          x2={width}
          y2={height / 2}
          stroke="var(--line)"
          strokeWidth={1}
          strokeDasharray="3 3"
        />
      </svg>
    )
  }

  const min = Math.min(...data)
  const max = Math.max(...data)
  const span = max - min || 1
  const stepX = width / (data.length - 1)
  const pad = strokeWidth + 1

  const points = data.map((v, i) => {
    const x = i * stepX
    const y = pad + (height - pad * 2) * (1 - (v - min) / span)
    return [x, y] as const
  })

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p[0].toFixed(2)},${p[1].toFixed(2)}`).join(' ')
  const areaPath = `${linePath} L${width},${height} L0,${height} Z`

  const stroke = color ?? (data[data.length - 1] >= data[0] ? 'var(--up)' : 'var(--down)')

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className={cn('block', className)}
      aria-hidden
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={stroke} stopOpacity={0.28} />
          <stop offset="100%" stopColor={stroke} stopOpacity={0} />
        </linearGradient>
      </defs>
      {area && <path d={areaPath} fill={`url(#${gradId})`} stroke="none" />}
      <path
        d={linePath}
        fill="none"
        stroke={stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}

export default Sparkline
