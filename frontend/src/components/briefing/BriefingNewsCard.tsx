/**
 * 주요 헤드라인 뉴스
 */
import { Newspaper } from 'lucide-react'
import { Badge, Card } from '../ui'
import { hasText } from './utils'
import type { Interactive } from './types'

export function BriefingNewsCard({ interactive }: { interactive?: Interactive }) {
  const news = (interactive?.news_headlines ?? []).filter((n) => n && hasText(n.title))
  if (news.length === 0) return null

  return (
    <Card
      eyebrow={
        <span className="inline-flex items-center gap-1.5">
          <Newspaper size={14} strokeWidth={2} />
          Headlines
        </span>
      }
      title="주요 헤드라인"
      action={<Badge tone="neutral">{news.length}건</Badge>}
    >
      <ul className="space-y-2.5">
        {news.map((n, i) => (
          <li
            key={`${n.title}-${i}`}
            className="flex gap-3 rounded-chip border border-line bg-card-2/40 px-3.5 py-2.5"
          >
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-pill bg-hanwha/12 font-mono text-[10px] font-bold text-hanwha">
              {i + 1}
            </span>
            <div className="min-w-0">
              <p className="text-sm font-medium leading-snug text-beige">{n.title}</p>
              {hasText(n.desc) && <p className="mt-0.5 text-xs text-muted">{n.desc}</p>}
            </div>
          </li>
        ))}
      </ul>
    </Card>
  )
}
