import { render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { describe, it, expect } from 'vitest'
import { LiveFeed } from './LiveFeed'

describe('LiveFeed', () => {
  it('renders agent messages with names', () => {
    const ref = createRef<HTMLDivElement>()
    render(<LiveFeed feedBottomRef={ref} messages={[
      { idx: 0, ts: '2026-06-09T10:00:00', agent: 'Macro PM', stage: 'discovery', text: 'VIX 안정', icon: 'activity' },
      { idx: 1, ts: '2026-06-09T10:00:02', agent: 'Bull 리서처', stage: 'sector_debate', text: '반도체 유망', icon: 'arrow' },
    ]} />)
    expect(screen.getByText('Macro PM')).toBeTruthy()
    expect(screen.getByText('반도체 유망')).toBeTruthy()
    expect(screen.getByText('2개 발언')).toBeTruthy()
  })
})
