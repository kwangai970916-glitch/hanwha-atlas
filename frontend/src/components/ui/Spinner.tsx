import { cn } from '../../lib/utils'

type SpinnerProps = {
  size?: number
  className?: string
}

/** 오렌지 액센트 스피너 (순수 SVG/CSS). */
export function Spinner({ size = 18, className }: SpinnerProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      className={cn('animate-spin text-hanwha', className)}
      role="status"
      aria-label="로딩 중"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeOpacity={0.2}
        strokeWidth="3"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  )
}

export default Spinner
