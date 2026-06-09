import { render, screen } from '@testing-library/react'
import { expect, test } from 'vitest'
import { BriefingReport } from './BriefingReport'
import type { ReportEnvelope } from './types'

const env: ReportEnvelope = {
  slot: 'close', persona: '강진혁', title: '마감·수급·판단', stance: 'RISK-OFF',
  headline: '핵심 요약', blocks: [
    { id: 'wrap', label: '마감 총평', type: 'paragraph', body: '문단 내용' },
    { id: 'flows', label: '주체별 수급', type: 'kv', body: [{ k: '외국인', v: '-3,000억', tone: 'down' }] },
    { id: 'sectors', label: '주도·부진 섹터', type: 'bullets', body: ['반도체 +1%', '2차전지 -2%'] },
  ],
}

test('renders persona, stance, headline and blocks', () => {
  render(<BriefingReport report={env} generatedAt={Date.now()} />)
  expect(screen.getByText('강진혁')).toBeInTheDocument()
  expect(screen.getByText('RISK-OFF')).toBeInTheDocument()
  expect(screen.getByText('핵심 요약')).toBeInTheDocument()
  expect(screen.getByText('마감 총평')).toBeInTheDocument()
  expect(screen.getByText('문단 내용')).toBeInTheDocument()
  expect(screen.getByText('외국인')).toBeInTheDocument()
  expect(screen.getByText('반도체 +1%')).toBeInTheDocument()
})
