/**
 * briefing/ 공유 유틸 함수
 */
import type { ReactNode } from 'react'
import type { Verdict } from './types'

/** 경과 초 → "MM:SS" */
export function formatElapsed(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = sec % 60
  return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

/** seconds_until → "N시간 M분" / "M분 S초" 카운트다운 문구 */
export function formatCountdown(sec: number): string {
  if (sec <= 0) return '곧 실행'
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  const s = sec % 60
  if (h > 0) return `${h}시간 ${m}분 후`
  if (m > 0) return `${m}분 ${String(s).padStart(2, '0')}초 후`
  return `${s}초 후`
}

/** ISO8601(KST) → "MM/DD HH:mm" */
export function formatTs(ts?: string): string {
  if (!ts) return '—'
  try {
    const d = new Date(ts)
    if (Number.isNaN(d.getTime())) return ts.slice(5, 16).replace('T', ' ')
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    const hh = String(d.getHours()).padStart(2, '0')
    const mi = String(d.getMinutes()).padStart(2, '0')
    return `${mm}/${dd} ${hh}:${mi}`
  } catch {
    return ts
  }
}

/** stance 문자열 → 배지 톤(한국 관례: 강세=레드 up, 약세=블루 down) */
export function stanceTone(stance?: string): {
  tone: 'up' | 'down' | 'neutral' | 'hanwha'
  label: string
} {
  const s = (stance || '').toUpperCase()
  if (/BULL|RISK[- ]?ON|강세|매수|OVERWEIGHT|POSITIVE/.test(s))
    return { tone: 'up', label: stance || '강세' }
  if (/BEAR|RISK[- ]?OFF|약세|매도|UNDERWEIGHT|NEGATIVE|CAUTION/.test(s))
    return { tone: 'down', label: stance || '약세' }
  if (/NEUTRAL|중립|HOLD/.test(s)) return { tone: 'neutral', label: stance || '중립' }
  return { tone: 'hanwha', label: stance || '—' }
}

export const hasText = (v?: string) => typeof v === 'string' && v.trim().length > 0

/** 위원회 최종 결정 판정 (한국 관례: BUY=레드 up / SELL=블루 down / HOLD=중립) */
export function classifyDecision(decision?: string | null): Verdict {
  const d = (decision ?? '').toUpperCase()
  if (d.includes('BUY') || d.includes('매수')) return 'buy'
  if (d.includes('SELL') || d.includes('매도')) return 'sell'
  return 'hold'
}

/** final_trade_decision 요약 앞부분 추출 */
export function summarizeDecision(text?: string, max = 260): string {
  if (!hasText(text)) return ''
  const cleaned = text!
    .replace(/```[\s\S]*?```/g, ' ')
    .replace(/[#>*_`-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
  if (cleaned.length <= max) return cleaned
  return cleaned.slice(0, max).trimEnd() + '…'
}

/** verdict → 메타데이터 (아이콘은 호출측에서 주입) */
export type VerdictMeta = {
  label: string
  tone: 'up' | 'down' | 'neutral'
  text: string
  ring: string
  surface: string
}

export const VERDICT_STYLE: Record<Verdict, VerdictMeta> = {
  buy: {
    label: 'BUY · 매수',
    tone: 'up',
    text: 'text-up',
    ring: 'border-up/30',
    surface: 'bg-up/[0.07]',
  },
  sell: {
    label: 'SELL · 매도',
    tone: 'down',
    text: 'text-down',
    ring: 'border-down/30',
    surface: 'bg-down/[0.07]',
  },
  hold: {
    label: 'HOLD · 관망',
    tone: 'neutral',
    text: 'text-greige',
    ring: 'border-line',
    surface: 'bg-card-2/40',
  },
}

/** 슬롯 ID → 한국어 라벨 */
export const SLOT_LABEL: Record<string, string> = {
  premarket: '장전',
  intraday: '장중',
  close: '장마감',
}

/** 브랜드 토큰 → 차트 색 (CSS 변수만, 하드코딩 hex 금지) */
export const C = {
  hanwha: 'var(--hanwha)',
  up: 'var(--up)',
  down: 'var(--down)',
  blue: 'var(--blue)',
  purple: 'var(--purple)',
  greige: 'var(--greige)',
  beige: 'var(--beige)',
  muted: 'var(--muted)',
  line: 'var(--line)',
  card: 'var(--card)',
} as const

/** 9섹션 LLM 모델 표기 */
export const LLM_MODEL = 'MiMo V2.5'

/** framer-motion stagger 컨테이너/아이템 변형 */
export const containerVariants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
}
export const itemVariants = {
  hidden: { opacity: 0, y: 10 },
  show: {
    opacity: 1,
    y: 0,
    transition: { type: 'spring' as const, stiffness: 260, damping: 26 },
  },
}

/** 폴링 상수: 시황 생성 완료 감지는 빠릿하게. 전체 타임아웃은 약 6분 유지. */
export const POLL_INTERVAL_MS = 1500
export const MAX_POLLS = 240

// ReactNode를 유틸에서 직접 import해 VERDICT_META 아이콘을 제거했으므로
// 아이콘은 CommitteeLatestCard 내에서 인라인으로 삽입합니다.
export type { ReactNode }
