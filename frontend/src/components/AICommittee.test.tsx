import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import { AICommittee } from './AICommittee'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('renders convene panel (title, input, CTA, idle empty state)', () => {
  render(<AICommittee apiBase="http://127.0.0.1:8000" />)
  expect(screen.getByText('AI 투자위원회')).toBeInTheDocument()
  expect(screen.getByPlaceholderText(/종목 입력/)).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /위원회 소집/ })).toBeInTheDocument()
  expect(screen.getByText('위원회 심의 진행')).toBeInTheDocument()
})

test('소집 triggers committee run and shows in-session progress', async () => {
  const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.includes('/api/committee/run')) {
      return Promise.resolve(new Response(JSON.stringify({ job_id: 'job_test_1', ticker: '삼성전자' })))
    }
    if (url.includes('/api/committee/status')) {
      return Promise.resolve(new Response(JSON.stringify({ stage: 'running', ticker: '005930.KS' })))
    }
    return Promise.resolve(new Response(JSON.stringify({})))
  })

  render(<AICommittee apiBase="http://127.0.0.1:8000" />)
  fireEvent.click(screen.getByRole('button', { name: /위원회 소집/ }))

  // POST /api/committee/run 이 호출되고 심의 진행 UI로 전환
  await waitFor(() =>
    expect(fetchSpy.mock.calls.some(c => String(c[0]).includes('/api/committee/run'))).toBe(true),
  )
  expect(await screen.findByText('위원회 심의 진행')).toBeInTheDocument()
  // 4단계 파이프라인 라벨 표시
  expect(screen.getByText('애널리스트 조사')).toBeInTheDocument()
  expect(screen.getByText('Bull / Bear 토론')).toBeInTheDocument()
})

test('renders final decision banner and report tabs when done', async () => {
  vi.spyOn(globalThis, 'fetch').mockImplementation((input) => {
    const url = String(input)
    if (url.includes('/api/committee/run')) {
      return Promise.resolve(new Response(JSON.stringify({ job_id: 'job_done', ticker: '삼성전자' })))
    }
    if (url.includes('/api/committee/status')) {
      return Promise.resolve(new Response(JSON.stringify({ stage: 'done', ticker: '005930.KS' })))
    }
    if (url.includes('/api/committee/result')) {
      return Promise.resolve(new Response(JSON.stringify({
        ticker: '005930.KS',
        input: '삼성전자',
        is_kr: true,
        decision: 'HOLD — 중장기 관점 유지, 분할 접근 권고',
        reports: {
          final_trade_decision: '# 최종결정\n중장기 관점에서 관망 후 분할 접근 권고.',
          market_report: '## 기술적\nRSI 중립.',
        },
      })))
    }
    return Promise.resolve(new Response(JSON.stringify({})))
  })

  render(<AICommittee apiBase="http://127.0.0.1:8000" />)
  fireEvent.click(screen.getByRole('button', { name: /위원회 소집/ }))

  // 폴링(5s) 후 done → 결과 배너/리포트. 타임아웃 넉넉히.
  // 'HOLD'는 배너 라벨/Decision Raw 양쪽에 나타나므로 고유 라벨로 좁힌다.
  expect(
    await screen.findByText('HOLD · 관망', {}, { timeout: 8000 }),
  ).toBeInTheDocument()
  // 리포트 탭 버튼(마크다운 h1과 중복되지 않도록 role로 좁힘)
  expect(screen.getByRole('button', { name: /최종결정/ })).toBeInTheDocument()
  // 마크다운 본문이 렌더됨
  expect(screen.getByText(/중장기 관점에서 관망/)).toBeInTheDocument()
}, 12000)
