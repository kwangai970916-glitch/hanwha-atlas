// 오프라인(제출용) 모드: 모든 /api fetch와 EventSource를 캡처된 fixture로 가로채
// 백엔드 없이도 전 탭이 에러 없이 동작하게 한다. 미매칭 엔드포인트는 graceful empty.
/* eslint-disable @typescript-eslint/no-explicit-any */
import fixtures from './fixtures'

const F = fixtures as Record<string, any>

// ── 항목1: 브리핑 job 상태 추적 (slot → pollCount) ──────────────────────────
const briefingJobs: Record<string, number> = {}

// ── 항목4: 위원회 messages 폴링 횟수 추적 ────────────────────────────────────
let committeeCallCount = 0
let ideaCallCount = 0

function pathOf(input: any): string {
  try {
    const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input?.url ?? ''
    return new URL(u, 'http://x').pathname
  } catch {
    return String(input)
  }
}

function queryOf(input: any): URLSearchParams {
  try {
    const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input?.url ?? ''
    return new URL(u, 'http://x').searchParams
  } catch {
    return new URLSearchParams()
  }
}

function jsonResp(data: any, status = 200): Response {
  return new Response(JSON.stringify(data ?? {}), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// ── 항목1: 브리핑 완료 응답 합성 ─────────────────────────────────────────────
// BriefingStatus 타입: success, slot, sections, report, png_path, png_paths
function makeBriefingDone(slot: string): any {
  const latest = F['/api/briefing/latest'] || {}
  // ReportEnvelope 형태의 합성 report
  const report = {
    slot: slot,
    persona: slot === 'premarket' ? '장전 브리핑' : slot === 'intraday' ? '장중 브리핑' : '마감 브리핑',
    title: slot === 'premarket' ? '장전 시황 브리핑' : slot === 'intraday' ? '장중 시황 브리핑' : '마감 시황 브리핑',
    stance: 'RISK-ON' as const,
    headline: latest.decision_summary || 'RISK-ON — 반도체·AI 주도주 강세 지속, 선별적 비중 확대 전략',
    as_of: '2026-06-09',
    blocks: [
      {
        id: 'stance',
        label: '시장 스탠스',
        type: 'kv' as const,
        body: [
          { k: '스탠스', v: 'RISK-ON', tone: 'up' as const },
          { k: '기준일', v: '2026-06-09', tone: 'neutral' as const },
        ],
      },
      {
        id: 'summary',
        label: '핵심 요약',
        type: 'paragraph' as const,
        body: latest.decision_summary || '반도체·AI 주도주 중심의 강세 흐름이 지속되고 있습니다. KOSPI 8,096p 수준에서 외국인 순매수세가 유입되며 지수를 지지하고 있습니다.',
      },
      {
        id: 'strategy',
        label: '운용 전략',
        type: 'bullets' as const,
        body: [
          '반도체(삼성전자·SK하이닉스) 비중 유지, 단기 조정 시 추가 매수 검토',
          '방산·조선 섹터 모멘텀 지속, 한화에어로스페이스 주목',
          '금융주 배당 매력 재부각 — KB금융·신한지주 관심',
        ],
      },
    ],
    legacy: latest.sections || {},
  }
  return {
    success: true,
    slot,
    report,
    sections: latest.sections || null,
    png_path: null,
    png_paths: [],
    // OFFLINE_BRIEFING_DONE_MARKER (검증용)
  }
}

// ── 항목2: holding-series 합성 (결정적 랜덤워크) ─────────────────────────────
// HoldingSeriesData: { name, dates, price_index, bm_index, bm_name, as_of }
function makeHoldingSeries(key: string, period: string): any {
  const nMap: Record<string, number> = { '1M': 22, '3M': 66, '1Y': 252, 'MAX': 252 }
  const n = nMap[period] || 252
  const dates: string[] = []
  const price_index: number[] = []
  const bm_index: number[] = []

  // 결정적 시드: key의 charCode 합
  let seed = 0
  for (let i = 0; i < key.length; i++) seed += key.charCodeAt(i)

  // 간단한 LCG pseudo-random
  function rng(): number {
    seed = (seed * 1664525 + 1013904223) & 0xffffffff
    return (seed >>> 0) / 0xffffffff
  }

  const baseDate = new Date('2026-06-09')
  let price = 100
  let bm = 100

  for (let i = n - 1; i >= 0; i--) {
    const d = new Date(baseDate)
    d.setDate(d.getDate() - i)
    // skip weekends
    if (d.getDay() === 0 || d.getDay() === 6) continue
    const yyyy = d.getFullYear()
    const mm = String(d.getMonth() + 1).padStart(2, '0')
    const dd = String(d.getDate()).padStart(2, '0')
    dates.push(`${yyyy}-${mm}-${dd}`)
    const dr = (rng() - 0.48) * 0.03
    const br = (rng() - 0.48) * 0.02
    price = Math.max(70, Math.min(150, price * (1 + dr)))
    bm = Math.max(80, Math.min(130, bm * (1 + br)))
    price_index.push(Math.round(price * 100) / 100)
    bm_index.push(Math.round(bm * 100) / 100)
  }

  // OFFLINE_HOLDING_SERIES_MARKER (검증용)
  return {
    name: key,
    dates,
    price_index,
    bm_index,
    bm_name: 'KOSPI',
    as_of: '2026-06-09',
  }
}

// ── 항목4: committee/latest reports → messages 배열 합성 ─────────────────────
function committeeReportsToMessages(latest: any): any[] {
  if (!latest) return []
  const msgs: any[] = []
  const reports = latest.reports || {}
  let idx = 0
  const ts = new Date().toISOString()
  if (latest.ticker || latest.input) {
    msgs.push({ idx: idx++, ts, agent: '사회자', stage: 'intro', text: `${latest.input || latest.ticker} 종목 투자심의위원회를 시작합니다.`, icon: 'users' })
  }
  for (const [key, val] of Object.entries(reports)) {
    const label = key === 'final_trade_decision' ? '최종 투자의견' : key.replace(/_/g, ' ')
    const text = typeof val === 'string' ? val.slice(0, 200) : String(val)
    msgs.push({ idx: idx++, ts, agent: label, stage: 'report', text, icon: 'file-text' })
  }
  if (latest.decision) {
    msgs.push({ idx: idx++, ts, agent: '위원장', stage: 'decision', text: `최종 결정: ${latest.decision}`, icon: 'gavel' })
  }
  return msgs
}

// ── 항목3/4: since 파라미터 슬라이싱 + 점진 방출 ────────────────────────────
function minutesToMessages(latest: any): any[] {
  const mins: any[] = (latest && latest.committee_minutes) || []
  return mins.map((m: any, i: number) => ({
    idx: i,
    ts: latest?.generated_at || '',
    agent: m.agent,
    stage: m.stage,
    text: m.text,
    icon: m.icon || 'message',
  }))
}

// ── 항목5: schedule next_epoch 동적 보정 ────────────────────────────────────
function fixSchedule(sched: any): any {
  if (!sched || !sched.slots) return sched
  const now = Date.now()
  const fixedSlots = sched.slots.map((s: any, i: number) => {
    // 각 slot을 현재 기준 1h, 2.5h, 10.5h 후로 설정
    const offsets = [1 * 3600, 2.5 * 3600, 10.5 * 3600]
    const offset = offsets[i] ?? ((i + 1) * 3600)
    const next_epoch = (now / 1000) + offset
    const next_ts = new Date(next_epoch * 1000).toISOString()
    const seconds_until = Math.round(offset)
    return { ...s, next_epoch, next_ts, seconds_until }
  })
  return { ...sched, slots: fixedSlots }
}

function resolve(path: string, input?: any, init?: any): any {
  // ── 브리핑 생성 POST 감지 → job 등록 ──────────────────────────────────────
  if (/^\/api\/briefing\/[^/]+$/.test(path) && init?.method?.toUpperCase() === 'POST') {
    const slotMatch = path.match(/^\/api\/briefing\/([^/]+)$/)
    const slot = slotMatch ? slotMatch[1] : 'close'
    briefingJobs[slot] = 0
    return { job_id: `offline-${slot}`, slot, status: 'running' }
  }

  // ── 브리핑 status 폴링 → 2~3회 후 완료 ───────────────────────────────────
  if (/^\/api\/briefing\/[^/]+\/status$/.test(path)) {
    const slotMatch = path.match(/^\/api\/briefing\/([^/]+)\/status$/)
    const slot = slotMatch ? slotMatch[1] : 'close'
    if (slot in briefingJobs) {
      briefingJobs[slot] = (briefingJobs[slot] || 0) + 1
      if (briefingJobs[slot] >= 2) {
        // 완료 응답 반환
        delete briefingJobs[slot]
        return makeBriefingDone(slot)
      }
      return { status: 'running', progress: briefingJobs[slot] * 40 }
    }
    return { status: 'idle' }
  }

  // ── 위원회/아이디어 위원회 비동기 플로우 합성 (즉시 완료) ──────────────────
  if (path === '/api/idea/committee/run') return { job_id: 'offline', keywords: '' }
  if (path === '/api/committee/run') return { job_id: 'offline', ticker: '오프라인' }
  if (path === '/api/idea/committee/status') return { stage: 'done', stage_label: '회의 완료', step: 5 }
  if (path === '/api/committee/status') return { stage: 'done', stage_label: '심의 완료', step: 4 }
  if (path === '/api/idea/committee/result') return F['/api/idea/committee/latest']
  if (path === '/api/committee/result') return F['/api/committee/latest']

  // ── 항목3: idea committee messages — since 슬라이싱 + 점진 방출 ─────────
  if (path.startsWith('/api/idea/committee/messages')) {
    const allMsgs = minutesToMessages(F['/api/idea/committee/latest'])
    const total = allMsgs.length
    ideaCallCount++
    // 점진 방출: 호출 횟수마다 5건씩 증가, 최대 total
    const reveal = Math.min(ideaCallCount * 5, total)
    const since = parseInt(queryOf(input).get('since') || '0', 10) || 0
    const sliced = allMsgs.slice(0, reveal).slice(since)
    return { messages: sliced, total }
  }

  // ── 항목4: committee messages — reports 합성 + since 슬라이싱 + 점진 방출 ─
  if (path.startsWith('/api/committee/messages')) {
    const allMsgs = committeeReportsToMessages(F['/api/committee/latest'])
    const total = allMsgs.length
    committeeCallCount++
    const reveal = Math.min(committeeCallCount * 2, total)
    const since = parseInt(queryOf(input).get('since') || '0', 10) || 0
    const sliced = allMsgs.slice(0, reveal).slice(since)
    return { messages: sliced, total }
  }

  // ── 항목2: holding-series 합성 ───────────────────────────────────────────
  if (path === '/api/pnl/holding-series') {
    const params = queryOf(input)
    const key = params.get('key') || 'holding'
    const period = params.get('period') || '1Y'
    return makeHoldingSeries(key, period)
  }

  // ── 항목5: schedule next_epoch 보정 ─────────────────────────────────────
  if (path === '/api/briefing/schedule') {
    return fixSchedule(F['/api/briefing/schedule'])
  }

  // ── 정확 일치 ──
  if (path in F) return F[path]

  // ── 경로 파라미터 와일드카드 ──
  if (path.startsWith('/api/market/intraday/')) return F['/api/market/intraday/*']
  if (path.startsWith('/api/market/candles/')) return F['/api/market/candles/*']
  if (/^\/api\/briefing\/[^/]+$/.test(path)) return F['/api/briefing/latest']

  // ── 폴백: 빈 객체 (절대 throw 없음) ──
  return {}
}

export function installOffline(): void {
  // 1) fetch 가로채기
  const realFetch = typeof window !== 'undefined' && window.fetch ? window.fetch.bind(window) : null
  ;(window as any).fetch = async (input: any, init?: any): Promise<Response> => {
    const path = pathOf(input)
    if (path.startsWith('/api/')) {
      try {
        return jsonResp(resolve(path, input, init))
      } catch {
        return jsonResp({})
      }
    }
    if (realFetch) return realFetch(input, init)
    return jsonResp({})
  }

  // 2) EventSource(시장 스트림) — 캡처 스냅샷 1회 emit 후 조용히 유지
  const snapshot = F['/api/market/snapshot']
  class OfflineEventSource {
    onmessage: ((e: any) => void) | null = null
    onerror: ((e: any) => void) | null = null
    onopen: ((e: any) => void) | null = null
    readyState = 1
    url: string
    private listeners: Record<string, Array<(e: any) => void>> = {}
    constructor(url: string) {
      this.url = String(url)
      setTimeout(() => {
        this.dispatch('open', {})
        if (this.url.includes('/api/market/stream') && snapshot) {
          this.dispatch('message', { data: JSON.stringify(snapshot) })
        }
      }, 50)
    }
    private dispatch(type: string, e: any) {
      if (type === 'message' && this.onmessage) this.onmessage(e)
      if (type === 'open' && this.onopen) this.onopen(e)
      if (type === 'error' && this.onerror) this.onerror(e)
      ;(this.listeners[type] || []).forEach((cb: (e: any) => void) => cb(e))
    }
    addEventListener(type: string, cb: (e: any) => void) {
      if (!this.listeners[type]) this.listeners[type] = []
      this.listeners[type].push(cb)
    }
    removeEventListener() {}
    close() {
      this.readyState = 2
    }
  }
  ;(window as any).EventSource = OfflineEventSource as any

  // 3) 깨진 이미지(오프라인에서 못 불러오는 /illustrations 등)는 조용히 숨김 — 에러 표시 방지
  window.addEventListener(
    'error',
    (e: any) => {
      const t = e?.target
      if (t && t.tagName === 'IMG') {
        t.style.visibility = 'hidden'
      }
    },
    true,
  )
}
