import type { ReactNode } from 'react'
import { AlertTriangle } from 'lucide-react'
import { cn } from '../../lib/utils'

type ErrorStateProps = {
  title?: ReactNode
  message?: ReactNode
  /** 재시도 핸들러 — 있으면 재시도 버튼 노출 */
  onRetry?: () => void
  retryLabel?: string
  className?: string
}

/** 에러 상태 — 비동기 뷰 3종 중 하나. up(레드) 톤 경고. */
export function ErrorState({
  title = '문제가 발생했습니다',
  message = '데이터를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.',
  onRetry,
  retryLabel = '다시 시도',
  className,
}: ErrorStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-card border border-up/25 bg-up/[0.06] px-6 py-10 text-center',
        className,
      )}
    >
      <div className="grid h-11 w-11 place-items-center rounded-pill bg-up/12 text-up">
        <AlertTriangle size={20} strokeWidth={1.9} />
      </div>
      <div>
        <p className="font-display text-sm font-bold text-beige">{title}</p>
        <p className="mt-1 max-w-sm text-xs text-muted">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="mt-1 rounded-chip border border-line bg-card-2 px-3.5 py-1.5 text-xs font-semibold text-beige transition-colors hover:border-hanwha hover:text-hanwha"
        >
          {retryLabel}
        </button>
      )}
    </div>
  )
}

export default ErrorState
