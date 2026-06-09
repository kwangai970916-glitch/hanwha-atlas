/**
 * MarketNewsFlow — 상장주식 실시간 뉴스 피드
 * - /api/market/news 2분 자동 갱신
 * - 종목 태그 클릭 → 아이디어랩 이동
 * - "보유주식만" 필터 → /api/pnl 보유종목 코드로 필터링
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Briefcase, ExternalLink, FileText, RefreshCw, Rss, TrendingUp } from 'lucide-react'
import { Card, Spinner, ErrorState } from '../ui'
import { cn } from '../../lib/utils'

const REFRESH_MS = 120_000 // 2분

type StockTag = { name: string; code: string }
type NewsItem = {
  title: string
  url?: string
  time?: string
  stocks: StockTag[]
  source?: string
  type?: 'dart' | 'news'
}
type NewsResponse = { items?: NewsItem[]; total?: number; cached?: boolean }
type PnlHolding = { live_code?: string | null; name?: string }
type PnlResponse = { holdings?: PnlHolding[] }

export function MarketNewsFlow({
  apiBase,
  onStockClick,
  showTitle = true,
  feedMaxH,
}: {
  apiBase: string
  onStockClick?: (code: string, name: string) => void
  showTitle?: boolean
  /** 피드 리스트 최대 높이(px) — 초과 시 내부 스크롤 */
  feedMaxH?: number
}) {
  const [items, setItems] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const [newCount, setNewCount] = useState(0)
  const timerRef = useRef<number | null>(null)
  const prevTitlesRef = useRef<Set<string>>(new Set())

  // 보유주식 필터
  const [holdingFilter, setHoldingFilter] = useState(false)
  const [holdingCodes, setHoldingCodes] = useState<Set<string>>(new Set())
  const [holdingLoading, setHoldingLoading] = useState(false)

  const load = useCallback(async () => {
    try {
      const r = await fetch(`${apiBase}/api/market/news?limit=40`)
      if (!r.ok) throw new Error(`${r.status}`)
      const d: NewsResponse = await r.json()
      const fetched = d.items ?? []

      const prevTitles = prevTitlesRef.current
      const fresh = fetched.filter(i => !prevTitles.has(i.title))
      if (prevTitles.size > 0 && fresh.length > 0) {
        setNewCount(fresh.length)
        setTimeout(() => setNewCount(0), 4000)
      }
      prevTitlesRef.current = new Set(fetched.map(i => i.title))

      setItems(fetched)
      setLastUpdated(new Date())
      setError(false)
    } catch {
      setError(true)
    } finally {
      setLoading(false)
    }
  }, [apiBase])

  useEffect(() => {
    load()
    timerRef.current = window.setInterval(load, REFRESH_MS)
    return () => { if (timerRef.current) window.clearInterval(timerRef.current) }
  }, [load])

  // 보유주식 필터 토글
  const toggleHoldingFilter = async () => {
    const next = !holdingFilter
    setHoldingFilter(next)
    if (next && holdingCodes.size === 0) {
      setHoldingLoading(true)
      try {
        const r = await fetch(`${apiBase}/api/pnl`)
        if (r.ok) {
          const d: PnlResponse = await r.json()
          const codes = new Set(
            (d.holdings ?? []).map(h => h.live_code).filter(Boolean) as string[]
          )
          setHoldingCodes(codes)
        }
      } catch { /* 실패해도 필터만 무시 */ }
      finally { setHoldingLoading(false) }
    }
  }

  const handleStockClick = (tag: StockTag) => {
    window.dispatchEvent(new CustomEvent('market:select-symbol', {
      detail: { code: tag.code, name: tag.name },
    }))
    onStockClick?.(tag.code, tag.name)
  }

  // 필터 적용
  const displayed = holdingFilter && holdingCodes.size > 0
    ? items.filter(item => item.stocks.some(s => holdingCodes.has(s.code)))
    : items

  return (
    <Card
      eyebrow={showTitle ? 'Live Market News' : undefined}
      title={showTitle ? '상장주식 실시간 뉴스' : undefined}
      action={
        <div className="flex items-center gap-2">
          {/* 보유주식만 필터 토글 */}
          <button
            onClick={toggleHoldingFilter}
            disabled={holdingLoading}
            title="보유주식 관련 뉴스만 보기"
            className={cn(
              'flex items-center gap-1 rounded-[8px] border px-2 py-1 font-mono text-[10px] font-semibold transition-colors disabled:opacity-50',
              holdingFilter
                ? 'border-hanwha/60 bg-hanwha/20 text-hanwha'
                : 'border-line bg-card-2/50 text-muted hover:border-hanwha/40 hover:text-hanwha',
            )}
          >
            {holdingLoading
              ? <RefreshCw size={10} className="animate-spin" />
              : <Briefcase size={10} strokeWidth={2} />
            }
            보유주식만
          </button>

          {newCount > 0 && (
            <motion.span
              initial={{ opacity: 0, scale: 0.8 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0 }}
              className="rounded-pill border border-up/40 bg-up/10 px-2 py-0.5 font-mono text-[10px] font-bold text-up"
            >
              +{newCount} 신규
            </motion.span>
          )}
          {lastUpdated && (
            <span className="font-mono text-[10px] text-muted">
              {lastUpdated.toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })} 갱신
            </span>
          )}
          <button
            onClick={load}
            disabled={loading}
            className="grid h-7 w-7 place-items-center rounded-[8px] border border-line bg-card-2/50 text-muted hover:text-hanwha disabled:opacity-40"
          >
            <RefreshCw size={12} className={cn(loading && 'animate-spin')} />
          </button>
        </div>
      }
    >
      {/* 보유주식 필터 활성 시 배지 */}
      {holdingFilter && (
        <div className="mb-3 flex items-center gap-1.5">
          <span className="h-1.5 w-1.5 rounded-full bg-hanwha" />
          <span className="font-mono text-[11px] text-hanwha">
            보유 {holdingCodes.size}종목 관련 뉴스만 표시
            {displayed.length === 0 && ' — 매칭 없음'}
          </span>
        </div>
      )}

      {loading && items.length === 0 && (
        <div className="flex items-center gap-2 py-6 text-sm text-muted">
          <Spinner size={14} />뉴스를 불러오는 중...
        </div>
      )}
      {error && items.length === 0 && (
        <ErrorState
          title="뉴스를 불러오지 못했습니다"
          message="네이버 금융 연결을 확인해주세요."
          onRetry={load}
          retryLabel="다시 시도"
          className="border-0 bg-transparent px-0 py-4"
        />
      )}
      {items.length > 0 && (
        <div
          className={cn('divide-y divide-line/40', feedMaxH && 'overflow-y-auto pr-1')}
          style={feedMaxH ? { maxHeight: feedMaxH } : undefined}
        >
          <AnimatePresence initial={false}>
            {displayed.map((item, idx) => (
              <motion.div
                key={item.title}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.18, delay: idx < 5 ? idx * 0.04 : 0 }}
                className="group py-3 first:pt-0"
              >
                <div className="flex items-start gap-3">
                  <span className={cn(
                    'mt-0.5 grid h-6 w-6 flex-shrink-0 place-items-center rounded-[6px] border transition-colors',
                    item.type === 'dart'
                      ? 'border-purple/40 bg-purple/10 text-purple'
                      : item.stocks.length > 0
                        ? 'border-hanwha/30 bg-hanwha/10 text-hanwha group-hover:bg-hanwha/20'
                        : 'border-line/60 bg-card-2/50 text-muted group-hover:border-hanwha/30 group-hover:text-hanwha',
                  )}>
                    {item.type === 'dart'
                      ? <FileText size={11} strokeWidth={2} />
                      : item.stocks.length > 0
                        ? <TrendingUp size={11} strokeWidth={2} />
                        : <Rss size={11} strokeWidth={2} />
                    }
                  </span>

                  <div className="min-w-0 flex-1">
                    {item.url ? (
                      <a
                        href={item.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="group/link inline-flex items-start gap-1 text-sm font-medium leading-snug text-greige hover:text-beige transition-colors"
                      >
                        <span className="line-clamp-2">{item.title}</span>
                        <ExternalLink size={11} className="mt-0.5 flex-shrink-0 opacity-0 group-hover/link:opacity-60 transition-opacity" />
                      </a>
                    ) : (
                      <p className="line-clamp-2 text-sm font-medium leading-snug text-greige">
                        {item.title}
                      </p>
                    )}

                    <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                      {item.time && (
                        <span className="font-mono text-[10px] text-muted/70">{item.time}</span>
                      )}
                      {item.stocks.map(tag => (
                        <button
                          key={tag.code}
                          onClick={() => handleStockClick(tag)}
                          className={cn(
                            'rounded-[5px] border px-1.5 py-0.5 font-mono text-[10px] font-semibold transition-colors',
                            holdingFilter && holdingCodes.has(tag.code)
                              ? 'border-hanwha bg-hanwha/30 text-hanwha hover:bg-hanwha hover:text-canvas'
                              : 'border-hanwha/30 bg-hanwha/10 text-hanwha hover:bg-hanwha hover:text-canvas',
                          )}
                          title={`${tag.name} AI 아이디어랩에서 보기`}
                        >
                          {tag.name}
                          {holdingFilter && holdingCodes.has(tag.code) && ' ★'}
                        </button>
                      ))}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
    </Card>
  )
}
