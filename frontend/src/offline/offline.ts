// 오프라인(제출용) 모드: 모든 /api fetch와 EventSource를 캡처된 fixture로 가로채
// 백엔드 없이도 전 탭이 에러 없이 동작하게 한다. 미매칭 엔드포인트는 graceful empty.
/* eslint-disable @typescript-eslint/no-explicit-any */
import fixtures from './fixtures'

const F = fixtures as Record<string, any>

function pathOf(input: any): string {
  try {
    const u = typeof input === 'string' ? input : input instanceof URL ? input.href : input?.url ?? ''
    return new URL(u, 'http://x').pathname
  } catch {
    return String(input)
  }
}

function jsonResp(data: any, status = 200): Response {
  return new Response(JSON.stringify(data ?? {}), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

// 아이디에이션 위원회 회의록(minutes) → 라이브 피드 messages 형태로 변환
function minutesToMessages(latest: any): any[] {
  const mins: any[] = (latest && latest.committee_minutes) || []
  return mins.map((m, i) => ({
    idx: i,
    ts: latest?.generated_at || '',
    agent: m.agent,
    stage: m.stage,
    text: m.text,
    icon: m.icon || 'message',
  }))
}

function resolve(path: string): any {
  // ── 위원회/아이디어 위원회 비동기 플로우 합성 (즉시 완료) ──
  if (path === '/api/idea/committee/run') return { job_id: 'offline', keywords: '' }
  if (path === '/api/committee/run') return { job_id: 'offline', ticker: '오프라인' }
  if (path === '/api/idea/committee/status') return { stage: 'done', stage_label: '회의 완료', step: 5 }
  if (path === '/api/committee/status') return { stage: 'done', stage_label: '심의 완료', step: 4 }
  if (path === '/api/idea/committee/result') return F['/api/idea/committee/latest']
  if (path === '/api/committee/result') return F['/api/committee/latest']
  if (path.startsWith('/api/idea/committee/messages'))
    return { messages: minutesToMessages(F['/api/idea/committee/latest']), total: 99 }
  if (path.startsWith('/api/committee/messages')) return { messages: [], total: 0 }

  // ── 정확 일치 ──
  if (path in F) return F[path]

  // ── 경로 파라미터 와일드카드 ──
  if (path.startsWith('/api/market/intraday/')) return F['/api/market/intraday/*']
  if (path.startsWith('/api/market/candles/')) return F['/api/market/candles/*']
  if (/^\/api\/briefing\/[^/]+\/status$/.test(path)) return F['/api/briefing/*/status']
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
        return jsonResp(resolve(path))
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
      ;(this.listeners[type] || []).forEach(cb => cb(e))
    }
    addEventListener(type: string, cb: (e: any) => void) {
      ;(this.listeners[type] ||= []).push(cb)
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
