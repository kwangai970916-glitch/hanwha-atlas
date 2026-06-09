import { useCallback, useEffect, useRef, useState } from 'react'
import { motion } from 'framer-motion'
import { ArrowUpRight, FileText, Newspaper, RefreshCw } from 'lucide-react'
import { Badge, Card, EmptyState, ErrorState, Skeleton } from './ui'
import { cn } from '../lib/utils'

type NewsItem = {
  time: string
  name: string
  title: string
  url?: string
  type: 'news' | 'dart'
}

type NewsResponse = {
  items?: NewsItem[]
}

type Holding = { name: string; code: string }

type NewsFlowProps = {
  apiBase: string
  /** 보유종목 목록 (name + KRX code). codes 미지정시 여기서 코드 추출 */
  holdings?: Holding[]
  /** holdings 대신 직접 코드 배열로 지정 가능 */
  codes?: string[]
  title?: string
  className?: string
}

const REFRESH_MS = 300_000

/** 공시=특수 카테고리(Point Purple), 뉴스=정보(Point Blue). 오렌지는 브랜드 전용. */
const TYPE_META = {
  dart: {
    label: '공시',
    tone: 'purple' as const,
    icon: FileText,
  },
  news: {
    label: '뉴스',
    tone: 'blue' as const,
    icon: Newspaper,
  },
}

/** 보유종목 뉴스/공시 피드. 한화 웜다크 터미널 카드. */
export function NewsFlow({
  apiBase,
  holdings,
  codes,
  title = '보유종목 뉴스 / 공시',
  className,
}: NewsFlowProps) {
  const codeList = (codes ?? holdings?.map(h => h.code) ?? []).filter(Boolean)
  const codeKey = codeList.join(',')

  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const [asOf, setAsOf] = useState<string | null>(null)
  const reqRef = useRef(0)

  const load = useCallback(
    async (initial: boolean) => {
      if (!codeKey) return
      const reqId = ++reqRef.current
      if (initial) {
        setLoading(true)
        setError(false)
      }
      try {
        const res = await fetch(`${apiBase}/api/pnl/news?codes=${codeKey}`)
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        const data: NewsResponse = await res.json()
        if (reqId !== reqRef.current) return
        setItems(data.items ?? [])
        setError(false)
        setAsOf(
          new Date().toLocaleTimeString('ko-KR', {
            hour: '2-digit',
            minute: '2-digit',
          }),
        )
      } catch {
        if (reqId !== reqRef.current) return
        if (initial) setError(true)
      } finally {
        if (reqId === reqRef.current && initial) setLoading(false)
      }
    },
    [apiBase, codeKey],
  )

  useEffect(() => {
    if (!codeKey) {
      setItems([])
      setLoading(false)
      setError(false)
      return
    }
    load(true)
    const t = setInterval(() => load(false), REFRESH_MS)
    return () => clearInterval(t)
  }, [codeKey, load])

  const action = (
    <div className="flex items-center gap-2.5">
      {asOf && !loading && !error && (
        <span className="hidden font-mono text-[10px] tabular-nums text-muted sm:inline">
          {asOf} 기준
        </span>
      )}
      <span className="inline-flex items-center gap-1.5 font-mono text-[10px] font-semibold uppercase tracking-[0.08em] text-hanwha">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full animate-pulse-soft rounded-full bg-hanwha/60" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-hanwha" />
        </span>
        Live
      </span>
      <button
        type="button"
        onClick={() => load(true)}
        disabled={loading || !codeKey}
        aria-label="새로고침"
        className="grid h-6 w-6 place-items-center rounded-chip border border-line bg-card-2 text-muted transition-colors hover:border-hanwha hover:text-hanwha disabled:cursor-not-allowed disabled:opacity-40"
      >
        <RefreshCw size={12} className={cn(loading && 'animate-spin')} />
      </button>
    </div>
  )

  return (
    <Card
      eyebrow="News & Filings"
      title={title}
      action={action}
      className={className}
      noPadding
    >
      <div className="max-h-72 overflow-y-auto px-5 pb-5">
        {/* 로딩 스켈레톤 */}
        {loading && items.length === 0 && (
          <div className="space-y-2.5 pt-1">
            {Array.from({ length: 5 }).map((_, i) => (
              <div
                key={i}
                className="flex items-start gap-3 rounded-chip border border-line/60 bg-card-2/30 p-3"
              >
                <Skeleton className="h-5 w-12 shrink-0" />
                <div className="min-w-0 flex-1 space-y-2">
                  <Skeleton className="h-3.5 w-full" />
                  <Skeleton className="h-3 w-2/5" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 에러 상태 */}
        {!loading && error && (
          <ErrorState
            title="뉴스를 불러오지 못했습니다"
            message="뉴스/공시 피드를 가져오는 중 문제가 발생했습니다."
            onRetry={() => load(true)}
            className="border-0 bg-transparent py-8"
          />
        )}

        {/* 빈 상태 */}
        {!loading && !error && items.length === 0 && (
          <EmptyState
            icon={<Newspaper size={20} strokeWidth={1.75} />}
            title="수집된 뉴스 없음"
            description={
              codeKey
                ? '보유종목 관련 최신 뉴스/공시가 아직 없습니다.'
                : '표시할 보유종목이 없습니다.'
            }
            className="border-0 bg-transparent py-8"
          />
        )}

        {/* 데이터 */}
        {!error && items.length > 0 && (
          <motion.ul
            initial="hidden"
            animate="show"
            variants={{
              hidden: {},
              show: { transition: { staggerChildren: 0.04 } },
            }}
            className="space-y-2"
          >
            {items.map((item, i) => {
              const meta = TYPE_META[item.type] ?? TYPE_META.news
              const Icon = meta.icon
              const Wrapper = item.url ? motion.a : motion.div
              return (
                <Wrapper
                  key={`${item.time}-${item.name}-${i}`}
                  {...(item.url
                    ? {
                        href: item.url,
                        target: '_blank',
                        rel: 'noopener noreferrer',
                      }
                    : {})}
                  variants={{
                    hidden: { opacity: 0, y: 8 },
                    show: { opacity: 1, y: 0 },
                  }}
                  whileHover={{ y: -2 }}
                  transition={{ type: 'spring', stiffness: 320, damping: 26 }}
                  className={cn(
                    'group flex items-start gap-3 rounded-chip border border-line/70 bg-card-2/40 p-3 transition-colors',
                    item.url
                      ? 'cursor-pointer hover:border-hanwha/40 hover:bg-card-2/70'
                      : 'cursor-default',
                  )}
                >
                  <Badge tone={meta.tone} className="mt-0.5 shrink-0">
                    <Icon size={11} strokeWidth={2} />
                    {meta.label}
                  </Badge>

                  <div className="min-w-0 flex-1">
                    <p className="line-clamp-2 text-sm leading-snug text-beige transition-colors group-hover:text-hanwha">
                      {item.title}
                    </p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1">
                      <span className="inline-flex items-center rounded-pill bg-card px-2 py-0.5 font-mono text-[10px] font-semibold tracking-[0.02em] text-greige">
                        {item.name}
                      </span>
                      <span className="font-mono text-[10px] tabular-nums text-muted">
                        {item.time}
                      </span>
                    </div>
                  </div>

                  {item.url && (
                    <ArrowUpRight
                      size={14}
                      className="mt-0.5 shrink-0 text-muted transition-colors group-hover:text-hanwha"
                    />
                  )}
                </Wrapper>
              )
            })}
          </motion.ul>
        )}
      </div>
    </Card>
  )
}

export default NewsFlow
