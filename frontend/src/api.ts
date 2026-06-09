export type StandardResponse = {
  intent: string
  result: Record<string, any>
  sources: Array<{ id: string; name: string; type: string; as_of: string }>
  as_of: string
  confidence: number
}

const API_BASE = import.meta.env.VITE_API_BASE ?? 'http://127.0.0.1:8000'

export async function runCommand(query: string): Promise<StandardResponse> {
  const response = await fetch(`${API_BASE}/api/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  })
  if (!response.ok) throw new Error(`Command failed: ${response.status}`)
  return response.json()
}

export async function generateReport(sourceResult: Record<string, any>): Promise<StandardResponse> {
  const response = await fetch(`${API_BASE}/api/report-generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ report_type: 'executive_summary', source_result: sourceResult, tone: '실장 보고' })
  })
  if (!response.ok) throw new Error(`Report failed: ${response.status}`)
  return response.json()
}

export async function evaluateIdea(symbol = '005930'): Promise<StandardResponse> {
  const response = await fetch(`${API_BASE}/api/ideas/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol })
  })
  if (!response.ok) throw new Error(`Idea evaluation failed: ${response.status}`)
  return response.json()
}


export async function securityAnalysis(symbol = '005930'): Promise<StandardResponse> {
  const response = await fetch(`${API_BASE}/api/research/security-analysis`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol })
  })
  if (!response.ok) throw new Error(`Security analysis failed: ${response.status}`)
  return response.json()
}

export async function dataStatus(): Promise<StandardResponse> {
  const response = await fetch(`${API_BASE}/api/data-status`)
  if (!response.ok) throw new Error(`Data status failed: ${response.status}`)
  return response.json()
}
