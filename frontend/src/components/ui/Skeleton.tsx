import { cn } from '../../lib/utils'

type SkeletonProps = {
  className?: string
}

/**
 * shimmer 로딩 스켈레톤. width/height 는 className 으로 지정.
 */
export function Skeleton({ className }: SkeletonProps) {
  return (
    <div
      className={cn(
        'relative overflow-hidden rounded-chip bg-card-2/60',
        'after:absolute after:inset-0 after:-translate-x-full after:animate-shimmer',
        'after:bg-gradient-to-r after:from-transparent after:via-beige/[0.06] after:to-transparent',
        className,
      )}
    />
  )
}

/** 여러 줄 텍스트 스켈레톤 헬퍼 */
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          className={cn('h-3.5', i === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  )
}

export default Skeleton
