import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

type CardProps = {
  title?: ReactNode
  /** 제목 옆 작은 설명 (kicker/eyebrow) */
  eyebrow?: ReactNode
  /** 우측 상단 액션 슬롯 */
  action?: ReactNode
  children?: ReactNode
  className?: string
  /** 내부 본문 패딩 제거 (표/차트 풀블리드용) */
  noPadding?: boolean
  /** 호버 마이크로 인터랙션 사용 여부 */
  hover?: boolean
}

/**
 * 웜다크 서피스 카드. 제목/액션 슬롯 옵션.
 * bg-card + 1px 웜브라운 보더 + 부드러운 그림자.
 */
export function Card({
  title,
  eyebrow,
  action,
  children,
  className,
  noPadding,
  hover = false,
}: CardProps) {
  return (
    <motion.section
      whileHover={hover ? { y: -2 } : undefined}
      transition={{ type: 'spring', stiffness: 280, damping: 26 }}
      className={cn(
        'group relative overflow-hidden rounded-[22px] border border-line/80 bg-card shadow-card',
        'before:pointer-events-none before:absolute before:inset-x-0 before:top-0 before:h-px before:bg-gradient-to-r before:from-transparent before:via-beige/18 before:to-transparent',
        'after:pointer-events-none after:absolute after:inset-0 after:bg-[radial-gradient(circle_at_12%_0%,rgba(243,115,33,0.08),transparent_32%)] after:opacity-70',
        className,
      )}
    >
      {(title || action || eyebrow) && (
        <header className="relative z-[1] flex items-start justify-between gap-4 px-5 pt-4 pb-3">
          <div className="min-w-0">
            {eyebrow && (
              <div className="mb-1 font-mono text-[11px] font-semibold uppercase tracking-[0.08em] text-hanwha">
                {eyebrow}
              </div>
            )}
            {title && (
              <h3 className="truncate font-display text-base font-bold tracking-tight text-beige">
                {title}
              </h3>
            )}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </header>
      )}
      <div className={cn('relative z-[1]', !noPadding && 'px-5 pb-5', !title && !noPadding && 'pt-5')}>
        {children}
      </div>
    </motion.section>
  )
}

export default Card
