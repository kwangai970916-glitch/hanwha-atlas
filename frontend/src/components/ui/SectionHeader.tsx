import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type SectionHeaderProps = {
  title: ReactNode
  /** 제목 위 작은 라벨 */
  eyebrow?: ReactNode
  /** 제목 아래 설명 */
  description?: ReactNode
  /** 우측 액션 슬롯 */
  action?: ReactNode
  className?: string
}

/** 섹션 헤더 — 오렌지 eyebrow + 디스플레이 폰트 타이틀 + 액션 슬롯. */
export function SectionHeader({
  title,
  eyebrow,
  description,
  action,
  className,
}: SectionHeaderProps) {
  return (
    <div className={cn('mb-4 flex items-end justify-between gap-4', className)}>
      <div className="min-w-0">
        {eyebrow && (
          <div className="mb-1.5 flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-hanwha">
            <span className="h-px w-6 bg-hanwha/60" />
            {eyebrow}
          </div>
        )}
        <h2 className="font-display text-xl font-bold tracking-tight text-beige">
          {title}
        </h2>
        {description && (
          <p className="mt-1 text-sm text-muted">{description}</p>
        )}
      </div>
      {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
    </div>
  )
}

export default SectionHeader
