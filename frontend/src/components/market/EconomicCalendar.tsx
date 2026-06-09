import { CalendarDays, Clock3, Globe2, Landmark, Zap } from 'lucide-react'
import { Badge, Card } from '../ui'
import { cn } from '../../lib/utils'

type Importance = 'high' | 'mid'

type CalendarEvent = {
  date: string
  timeKst: string
  country: 'US' | 'EU' | 'CN' | 'JP'
  title: string
  detail: string
  importance: Importance
  category: 'inflation' | 'fed' | 'growth' | 'labor' | 'sentiment'
}

const EVENTS: CalendarEvent[] = [
  { date: '2026-06-10', timeKst: '21:30', country: 'US', title: '미국 CPI / Core CPI', detail: '5월 물가 · 금리 기대 재가격 핵심', importance: 'high', category: 'inflation' },
  { date: '2026-06-11', timeKst: '21:30', country: 'US', title: '미국 PPI / 신규실업수당', detail: '생산자물가와 노동 둔화 동시 확인', importance: 'high', category: 'inflation' },
  { date: '2026-06-12', timeKst: '23:00', country: 'US', title: '미시간대 소비심리 예비치', detail: '기대인플레와 소비심리 체크', importance: 'mid', category: 'sentiment' },
  { date: '2026-06-16', timeKst: '21:30', country: 'US', title: '미국 소매판매', detail: '소비 모멘텀 · 경기 민감주 영향', importance: 'high', category: 'growth' },
  { date: '2026-06-18', timeKst: '03:00', country: 'US', title: 'FOMC 금리결정 / 점도표', detail: '6월 16~17일 회의 결과·파월 기자회견', importance: 'high', category: 'fed' },
  { date: '2026-06-25', timeKst: '21:30', country: 'US', title: 'GDP 확정치 / PCE 물가', detail: '성장률과 연준 선호 물가 확인', importance: 'high', category: 'growth' },
  { date: '2026-07-02', timeKst: '21:30', country: 'US', title: '비농업고용 / 실업률', detail: '7월 초 최대 노동시장 이벤트', importance: 'high', category: 'labor' },
]

const CATEGORY_META: Record<CalendarEvent['category'], { label: string; icon: typeof Globe2; tone: string }> = {
  inflation: { label: '물가', icon: Zap, tone: 'border-down/35 bg-down/10 text-down' },
  fed: { label: 'Fed', icon: Landmark, tone: 'border-hanwha/45 bg-hanwha/12 text-hanwha' },
  growth: { label: '성장', icon: Globe2, tone: 'border-blue/35 bg-blue/10 text-blue' },
  labor: { label: '고용', icon: CalendarDays, tone: 'border-up/35 bg-up/10 text-up' },
  sentiment: { label: '심리', icon: Clock3, tone: 'border-purple/35 bg-purple/10 text-purple' },
}

const IMPORTANCE_TEXT: Record<Importance, string> = { high: 'High', mid: 'Mid' }

function daysUntil(dateStr: string): number {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const target = new Date(`${dateStr}T00:00:00`)
  return Math.ceil((target.getTime() - today.getTime()) / 86_400_000)
}

function dateLabel(dateStr: string): string {
  return new Date(`${dateStr}T00:00:00`).toLocaleDateString('ko-KR', { month: 'short', day: 'numeric', weekday: 'short' })
}

function ddayLabel(days: number): string {
  if (days < 0) return '완료'
  if (days === 0) return '오늘'
  if (days === 1) return '내일'
  return `D-${days}`
}

export function EconomicCalendar() {
  const today = new Date().toISOString().slice(0, 10)
  const upcoming = EVENTS.filter(event => event.date >= today).sort((a, b) => a.date.localeCompare(b.date)).slice(0, 6)

  return (
    <Card className="h-full" eyebrow="Economic Calendar · US Focus" title="주요 경제 일정" action={<Badge tone="neutral">Investing.com형</Badge>}>
      <div className="flex min-h-[280px] flex-col gap-2.5">
        {upcoming.map(event => {
          const meta = CATEGORY_META[event.category]
          const Icon = meta.icon
          const days = daysUntil(event.date)
          const imminent = days <= 3

          return (
            <div key={`${event.date}-${event.title}`} className={cn('rounded-[14px] border p-3 transition-colors', imminent ? 'border-hanwha/35 bg-hanwha/[0.055]' : 'border-line/55 bg-card-2/25')}>
              <div className="flex items-start gap-3">
                <span className={cn('grid h-8 w-8 shrink-0 place-items-center rounded-[10px] border', meta.tone)}>
                  <Icon size={15} strokeWidth={2.2} />
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-[10px] font-bold text-hanwha">{event.country}</span>
                    <span className="truncate text-sm font-bold text-beige">{event.title}</span>
                    <span className={cn('ml-auto shrink-0 rounded-pill border px-2 py-0.5 font-mono text-[10px] font-bold', event.importance === 'high' ? 'border-down/35 bg-down/10 text-down' : 'border-line bg-card-2 text-muted')}>
                      {IMPORTANCE_TEXT[event.importance]}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-1 text-xs text-greige/80">{event.detail}</p>
                  <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-muted">
                    <span>{dateLabel(event.date)} · {event.timeKst} KST</span>
                    <span className={cn('font-bold', imminent ? 'text-hanwha' : 'text-muted')}>{ddayLabel(days)}</span>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default EconomicCalendar
