/**
 * briefing/ 공유 타입 정의
 * BriefingAgent 오케스트레이터 + 서브컴포넌트가 함께 사용.
 */

export type SlotId = 'premarket' | 'intraday' | 'close'
export type RunStatus = 'idle' | 'running' | 'done' | 'error'

export type Sections = {
  title?: string
  stance?: string
  key_issue?: string
  bull_case?: string
  bear_case?: string
  macro_flow?: string
  kr_outlook?: string
  strategy?: string
  news_flow?: string
}

export type RsPoint = { sector: string; rs_1d: number; rs_5d: number; quadrant?: string }
export type SectorReturn = { sector: string; change: number; contribution?: number; weight?: number }
export type NameChange = { name: string; change: number }
export type NewsHeadline = { title?: string; desc?: string }
export type AdrEntry = {
  date?: string
  kospi?: number | null
  kosdaq?: number | null
  kospi_adv?: number | null
  kospi_dec?: number | null
  kosdaq_adv?: number | null
  kosdaq_dec?: number | null
}
export type BreadthSide = {
  advance?: number | null
  decline?: number | null
  unchanged?: number | null
  total?: number | null
}

export type Interactive = {
  rs_kospi?: RsPoint[]
  rs_kosdaq?: RsPoint[]
  sector_returns?: SectorReturn[]
  kosdaq_sectors?: SectorReturn[]
  adr_history?: AdrEntry[]
  adr_latest?: AdrEntry
  breadth?: { kospi?: BreadthSide; kosdaq?: BreadthSide }
  top_gainers?: NameChange[]
  top_losers?: NameChange[]
  news_headlines?: NewsHeadline[]
  market_indices?: Record<string, unknown>
  error?: string
}

/** /status 응답 = run_briefing dict (생성 전엔 {status} 만). */
export type BriefingStatus = {
  status?: 'idle' | 'running'
  success?: boolean
  error?: string
  trace?: string
  slot?: string
  png_path?: string
  sections?: Sections
  market_data?: Record<string, unknown>
  interactive?: Interactive
  keys?: Record<string, unknown>
  report?: ReportEnvelope
  png_paths?: string[]
}

export type HistoryItem = {
  slot?: string
  ts?: string
  ts_epoch?: number
  decision_summary?: string | null
  png_path?: string
  success?: boolean
}

export type ScheduleItem = {
  slot: string
  label: string
  next_ts: string
  next_epoch: number
  seconds_until: number
}

/** GET /api/committee/latest 반환형 */
export type CommitteeLatest = {
  ticker?: string | null
  input?: string | null
  decision?: string | null
  reports?: Record<string, string>
  is_seed?: boolean
  available?: boolean
}

export type Verdict = 'buy' | 'sell' | 'hold'

// ── D1: Envelope types ────────────────────────────────────────────────────────
export type BlockType = 'bullets' | 'paragraph' | 'kv'
export type KvItem = { k: string; v: string; tone?: 'up' | 'down' | 'neutral' }
export type ReportBlock = {
  id: string
  label: string
  type: BlockType
  body: string | string[] | KvItem[]
}
export type ReportEnvelope = {
  slot: SlotId
  persona: string
  title: string
  stance: 'RISK-ON' | 'NEUTRAL' | 'RISK-OFF'
  headline: string
  blocks: ReportBlock[]
  as_of?: string
  legacy?: Record<string, string>
}
