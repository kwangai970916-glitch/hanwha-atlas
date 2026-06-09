import type { ReactNode } from 'react'
import { Inbox } from 'lucide-react'
import { cn } from '../../lib/utils'

type EmptyStateProps = {
  title?: ReactNode
  description?: ReactNode
  icon?: ReactNode
  action?: ReactNode
  className?: string
}

/** 빈 상태 — 비동기 뷰 3종(로딩/빈/에러) 중 하나. */
export function EmptyState({
  title = '데이터 없음',
  description = '표시할 항목이 아직 없습니다.',
  icon,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-3 rounded-card border border-dashed border-line bg-card/40 px-6 py-12 text-center',
        className,
      )}
    >
      <div className="grid h-11 w-11 place-items-center rounded-pill bg-card-2 text-muted">
        {icon ?? <Inbox size={20} strokeWidth={1.75} />}
      </div>
      <div>
        <p className="font-display text-sm font-bold text-beige">{title}</p>
        <p className="mt-1 text-xs text-muted">{description}</p>
      </div>
      {action}
    </div>
  )
}

export default EmptyState
