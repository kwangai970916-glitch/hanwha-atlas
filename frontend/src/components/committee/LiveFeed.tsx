import { motion, AnimatePresence } from 'framer-motion'
import {
  LineChart as LineChartIcon, HeartPulse, Newspaper, Landmark, ArrowUpRight,
  ArrowDownRight, Users, ShieldAlert, Briefcase, Gavel, MessagesSquare, Activity, Target,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

export type AgentMessage = { idx: number; ts: string; agent: string; stage: string; text: string; icon: string }

const AGENT_COLORS: Record<string, string> = {
  analysts: 'border-l-blue/60', research_debate: 'border-l-hanwha/70',
  risk_debate: 'border-l-yellow-500/70', decision: 'border-l-up/60',
  discovery: 'border-l-blue/60', sector_debate: 'border-l-hanwha/70',
  nomination: 'border-l-blue/60', risk_review: 'border-l-yellow-500/70',
}

const AGENT_ICONS: Record<string, ReactNode> = {
  '기술적 애널리스트': <LineChartIcon size={13} />, '심리 애널리스트': <HeartPulse size={13} />,
  '뉴스 애널리스트': <Newspaper size={13} />, '재무 애널리스트': <Landmark size={13} />,
  'Bull 리서처': <ArrowUpRight size={13} />, 'Bear 리서처': <ArrowDownRight size={13} />,
  '리서치 매니저': <Users size={13} />, '리스크 매니저': <ShieldAlert size={13} />,
  '투자위원회': <Users size={13} />, '트레이더': <Briefcase size={13} />, '최종 결정': <Gavel size={13} />,
  'Macro PM': <Activity size={13} />, '발굴 스카우트': <Target size={13} />,
  '스톡피커': <Target size={13} />, '공격 심의역': <ArrowUpRight size={13} />,
  '보수 심의역': <ShieldAlert size={13} />, '중립 심의역': <Users size={13} />,
  'PM 의장': <Gavel size={13} />,
}

export function LiveFeed({ messages, feedBottomRef }: {
  messages: AgentMessage[]; feedBottomRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
    <div className="mt-5">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Live Feed</span>
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-hanwha" />
        <span className="font-mono text-[10px] text-muted">{messages.length}개 발언</span>
      </div>
      <div className="max-h-72 space-y-2 overflow-y-auto rounded-[12px] border border-line/60 bg-canvas/30 p-3">
        <AnimatePresence initial={false}>
          {messages.map(m => (
            <motion.div key={m.idx} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22 }}
              className={cn('rounded-[9px] border border-line/50 bg-card-2/40 px-3 py-2.5 border-l-4',
                AGENT_COLORS[m.stage] ?? 'border-l-line')}>
              <div className="mb-1 flex items-center gap-1.5">
                <span className="text-muted">{AGENT_ICONS[m.agent] ?? <MessagesSquare size={13} />}</span>
                <span className="font-mono text-[11px] font-bold text-greige">{m.agent}</span>
                <span className="ml-auto font-mono text-[9px] text-muted/60">
                  {m.ts ? new Date(m.ts).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                </span>
              </div>
              <p className="text-[12px] leading-relaxed text-greige/90">{m.text}</p>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={feedBottomRef} />
      </div>
    </div>
  )
}
