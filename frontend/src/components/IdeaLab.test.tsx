import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { IdeaLab } from './IdeaLab'

const stockCandidates = Array.from({ length: 5 }).map((_, i) => ({
  route: ['Selective risk-on', '전력기기', '전력기기·전력망', `테스트픽${i + 1}`],
  pick_id: `p${i}`,
  symbol: `00000${i}`,
  name: `테스트픽${i + 1}`,
  theme: '전력기기·전력망',
  sector: '전력기기',
  score: 80 - i,
  discovery_score: 78,
  conviction_score: 76,
  thesis: '단기 모멘텀과 중기 thesis가 동시에 확인됩니다.',
  why_now: '뉴스·차트·수급·매크로가 함께 개선됩니다.',
  factor_scores: { chart: 80, supply_demand: 77, news: 78, macro: 81, valuation: 66, risk: 70 },
  evidence: [{ factor: 'macro', title: '매크로 궁합', detail: '전력수요와 맞습니다.' }],
  counter_evidence: ['과열 시 추격매수 리스크'],
  checklist: ['거래대금 유지 확인'],
  timing_signal: { signal: 'enter', reason: 'RSI 중립' },
}))

// decision.json = RadarResponse 상위호환 (위원회 결과)
const decision = {
  generated_at: '2026-06-09T09:00:00+09:00',
  horizon_months: 3,
  engine: 'ideation_committee',
  market_regime: {
    label: 'Selective risk-on',
    summary: '테마 확산과 뉴스 이벤트가 중요한 국면',
    news_keywords: ['AI 인프라', '전력망'],
  },
  pipeline: { summary: 'Selective risk-on 레짐에서 후보 5개를 채택했습니다.', stages: ['Macro', 'Sector', 'Stock'] },
  macro_flow: { label: 'Selective risk-on', summary: '테마 확산과 뉴스 이벤트가 중요한 국면', keywords: ['AI 인프라', '전력망'] },
  sector_flow: [
    { theme: '전력기기·전력망', sector: '전력기기', score: 82, news_score: 78, change: 1.4, foreign_flow: 'buy', macro_tags: ['전력수요'], why: '복합 팩터 강세' },
  ],
  news_flow: [{ title: '전력망 투자 사이클 장기화 전망', source: 'Sample News', published_at: '2026-06-09T08:00:00+09:00', symbols: ['267260'] }],
  themes: [{ theme: '전력기기·전력망', sector: '전력기기', score: 82, macro_tags: ['전력수요'], commentary: '복합 팩터 강세' }],
  top_picks: stockCandidates,
  stock_candidates: stockCandidates,
  committee_minutes: [
    { agent: 'Macro PM', stage: 'discovery', text: '위험선호 우호 국면입니다.', source: 'rules', icon: 'activity' },
    { agent: 'Bull 리서처', stage: 'sector_debate', text: '전력기기 레인이 유망합니다.', source: 'rules', icon: 'git-branch' },
    { agent: 'PM 의장', stage: 'decision', text: '후보 5개를 채택했습니다.', source: 'rules', icon: 'gavel' },
  ],
  transcript: [],
  data_quality: { mode: 'live', warnings: [] },
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('runs ideation committee via async job polling and renders results', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input, init) => {
    const url = String(input)
    if (url.includes('/api/idea/committee/run')) {
      expect((init?.method ?? 'GET')).toBe('POST')
      return Promise.resolve(new Response(JSON.stringify({ job_id: 'job_idea_1', keywords: '' })))
    }
    if (url.includes('/api/idea/committee/status')) {
      return Promise.resolve(new Response(JSON.stringify({ stage: 'done' })))
    }
    if (url.includes('/api/idea/committee/messages')) {
      return Promise.resolve(new Response(JSON.stringify({ messages: [], total: 0 })))
    }
    if (url.includes('/api/idea/committee/result')) {
      return Promise.resolve(new Response(JSON.stringify(decision)))
    }
    return Promise.resolve(new Response(JSON.stringify({})))
  })

  render(<IdeaLab apiBase="http://127.0.0.1:8000" />)

  expect(await screen.findByText('AI 아이디에이션 회의')).toBeInTheDocument()
  expect(screen.getByText('AI 서브에이전트 회의 진행')).toBeInTheDocument()
  // 자동 시작 꺼짐: 클릭 전에는 위원회 호출 없음
  expect(fetchMock.mock.calls.some(([i]) => String(i).includes('/api/idea/committee/run'))).toBe(false)

  fireEvent.click(screen.getByRole('button', { name: /회의 시작/ }))

  // POST /run 호출
  await waitFor(() =>
    expect(fetchMock.mock.calls.some(c => String(c[0]).includes('/api/idea/committee/run'))).toBe(true),
  )

  // 상태 폴링(5s) 후 done → 결과 렌더 (타임아웃 넉넉히)
  expect(await screen.findByText('회의 결론: Macro → Sector → Stock', {}, { timeout: 8000 })).toBeInTheDocument()
  expect(screen.getByText('뉴스가 연결한 섹터 레인')).toBeInTheDocument()
  expect(screen.getByText('투자 아이디어 후보')).toBeInTheDocument()
  expect(screen.getByText('테스트픽1 회의 결과')).toBeInTheDocument()
  expect(screen.getByText('회의 결과 메모')).toBeInTheDocument()

  await waitFor(() => expect(screen.getAllByText(/테스트픽/).length).toBeGreaterThanOrEqual(5))
  fireEvent.click(screen.getByRole('button', { name: /테스트픽2/ }))
  expect(await screen.findByText('테스트픽2 회의 결과')).toBeInTheDocument()
  expect(screen.getByText(/전력망 투자 사이클/)).toBeInTheDocument()

  // 옛 radar 동기 호출은 더 이상 없어야 한다
  expect(fetchMock.mock.calls.some(([i]) => String(i).includes('/api/idea/radar'))).toBe(false)
}, 12000)

test('loads cached committee result instantly via 최근 결과 button', async () => {
  const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.includes('/api/idea/committee/latest')) {
      return Promise.resolve(new Response(JSON.stringify(decision)))
    }
    return Promise.resolve(new Response(JSON.stringify({})))
  })

  render(<IdeaLab apiBase="http://127.0.0.1:8000" />)
  fireEvent.click(screen.getByRole('button', { name: '최근 결과' }))

  // /latest 1회로 즉시 결과 렌더 (라이브 run/폴링 없음)
  expect(await screen.findByText('회의 결론: Macro → Sector → Stock')).toBeInTheDocument()
  expect(screen.getByText('테스트픽1 회의 결과')).toBeInTheDocument()
  expect(fetchMock.mock.calls.some(([i]) => String(i).includes('/api/idea/committee/latest'))).toBe(true)
  expect(fetchMock.mock.calls.some(([i]) => String(i).includes('/api/idea/committee/run'))).toBe(false)
})
