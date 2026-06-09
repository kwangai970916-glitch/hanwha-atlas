import { render, screen, cleanup, fireEvent } from '@testing-library/react'
import { afterEach, expect, test, vi } from 'vitest'
import App from './App'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

test('dashboard renders core tabs including AI Committee', () => {
  render(<App />)
  expect(screen.getByText('ATLAS')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /시장현황/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /손익현황/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /시황에이전트/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /AI 아이디어랩/ })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /AI투자위원회/ })).toBeInTheDocument()
})

test('module tabs switch to AI Committee workbench', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({ result: { triggers: [] } })))
  render(<App />)
  fireEvent.click(screen.getByRole('button', { name: /AI투자위원회/ }))
  expect(await screen.findByText('AI 투자운용위원회', {}, { timeout: 5000 })).toBeInTheDocument()
  expect(screen.getByRole('button', { name: /위원회 소집/ })).toBeInTheDocument()
}, 10000)

test('professional separators are not corrupted', () => {
  render(<App />)
  expect(document.body.textContent).not.toContain(' ? ')
  expect(document.body.textContent).not.toContain('???')
  expect(document.body.textContent).toContain('Live / Sector / Chart')
})
