# AI Committee Design

## Goal
Add an "AI Committee" tab to AI Investment Desk OS that reviews a holding or investment idea from multiple agent perspectives and produces a PM-style committee memo for insurance general-account equity management.

## Source inspiration
The design borrows the multi-agent decision pattern from virattt/ai-hedge-fund, but does not embed the upstream runtime. The upstream project is an educational/research AI hedge fund with many investor-style agents plus fundamentals, technicals, valuation, risk manager, and portfolio manager agents. For this dashboard, we implement a deterministic sample-first committee workflow suitable for internal decision support, not trading automation.

## Scope
- Backend `POST /api/committee/review` for one symbol/idea.
- Backend `GET /api/committee/triggers` for automatic review alerts.
- Deterministic agent opinions with demo/sample fallback.
- Frontend tab `AI Committee` with symbol input, agent cards, risk review, PM summary, and memo.
- No real orders, no auto trading, no mandatory external LLM.

## Agents
- Fundamental
- Valuation
- Technical
- Sentiment / News
- Macro
- Risk Manager
- Bear Case
- Insurance PM

## Data flow
Frontend selects symbol/idea -> backend runner loads existing stock/sector/news/portfolio context -> agent functions produce opinions -> runner synthesizes final view and markdown memo -> frontend renders cards and memo.

## Non-goals
- Upstream repo full integration.
- Real PDF rendering in first pass.
- Autonomous order generation.
