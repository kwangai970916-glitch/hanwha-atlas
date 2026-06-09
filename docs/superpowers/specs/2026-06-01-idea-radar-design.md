# AI Idea Radar + Research Note Pipeline Design

Date: 2026-06-01
Status: approved for implementation

## Goal
Upgrade Idea Lab from a single-symbol idea/backtest page into a market-wide idea discovery pipeline. The page should answer: "What should we research today?" It must not rank stocks by relative strength alone. It should combine market-wide scanning, theme/keyword context, macro, news, chart/price action, supply-demand, valuation, and risk checks.

## Product Shape
Use Approach A: AI Idea Radar + Research Note Pipeline.

The user experience has four layers:
1. Market regime summary: risk-on/off style snapshot using macro proxies, market tone, and dominant news keywords.
2. Multi-factor theme/sector radar: theme cards scored by composite evidence, not RS only.
3. Top Picks 5: research-note cards for the five strongest candidates.
4. Idea history: saved ideas tracked for a default 3-month window with status and follow-up metrics.

## Scoring Philosophy
Use a two-stage gate.

### Discovery Gate
Find candidates from short-term signals:
- price/technical: RS, trend, breakout/volume, drawdown/overheat
- supply-demand: foreign/institutional net buy and continuity where data exists
- news/event: recent news, public disclosures, policy/order/earnings events
- theme breadth: whether a cluster is moving together, not a lone stock

### Conviction Gate
Promote only candidates with a medium-term thesis:
- macro fit: FX, rates, oil, risk appetite, sector sensitivity
- theme durability: whether the theme has follow-through potential
- valuation/fundamental sanity: PER/PBR/dividend or available pykrx fundamentals
- risk/counter-evidence: crowded trade, bad news, poor data coverage, weak thesis

Final score should expose factor breakdowns so users can see why a pick made the list.

## UI Design
Idea Lab should be reorganized into a workbench:
- Header: "AI Idea Radar" with description and actions: Run scan, Save snapshot.
- Controls: universe/market-wide mode, optional theme keywords, horizon default 3 months, top pick count fixed at 5.
- Market Regime panel: concise macro/news/market mood summary.
- Theme Radar panel: cards for leading themes/sectors with composite score, top factors, and representative symbols.
- Top Picks panel: five research-note cards. Each card includes symbol/name, score, action status, thesis, evidence by factor, counter-evidence, checklist, and buttons to save, open single-symbol idea, run backtest, or send to AI Committee where existing flows support it.
- History panel: persistent saved ideas with status (new, reviewing, watch, committee, adopted, rejected), created date, horizon end date, starting price, latest/placeholder performance, thesis watch flag, and notes.

## Data/API Design
Add backend support without breaking existing `/api/idea` and `/api/backtest`.

New endpoints:
- `GET /api/idea/radar`: returns market_regime, themes, top_picks, generated_at, horizon_months, factor weights, and data_quality.
- `GET /api/idea/history`: returns saved ideas.
- `POST /api/idea/history`: saves a research-note pick.
- `PATCH /api/idea/history/{idea_id}`: updates status/notes.

Persistence can use a JSON file under `backend/data/idea_history.json` for this iteration. The file must be created safely and tolerate missing/corrupt data by falling back to an empty list.

Radar generation should be deterministic and graceful when external data providers fail. Use existing pykrx/yfinance/news helpers where available, but provide a curated fallback universe and mockable deterministic scoring so tests and demos work without network/API keys.

## Components and Boundaries
Backend:
- `idea_radar.py`: radar generation, scoring, history storage helpers.
- `main.py`: thin FastAPI endpoints.

Frontend:
- Keep `IdeaLab.tsx` as page shell if practical, but split logic into small subcomponents if the file becomes unwieldy.
- Add types for RadarTheme, RadarPick, IdeaHistoryItem.
- Add state for radar loading/error, history loading/error, status update.

## Error Handling
- Radar scan failure should show an error card with retry, while existing single-idea/backtest tools remain usable.
- Partial data should be surfaced as data-quality warnings, not blank UI.
- Save/history operations should show clear success/failure state.

## Testing
Backend tests:
- radar endpoint returns 5 top picks and non-empty themes with factor breakdowns.
- history save/list/update works and survives missing storage file.
- scoring includes multiple factors and never labels RS as the only reason.

Frontend tests:
- Idea Lab renders AI Idea Radar, Theme Radar, Top Picks, and History sections.
- mocked radar response displays five research-note cards.
- save/history affordances render.

## Non-goals for this iteration
- Perfect real-time institutional alpha model.
- Full database migration.
- Automated order execution.
- Exact live performance tracking for every saved idea; include the history structure and start/latest fields, with graceful placeholders when latest price is unavailable.

## Acceptance Criteria
- User can run/view a composite market-wide radar and see Top Picks 5.
- Each Top Pick is a research note, not just a rank row.
- Theme radar explicitly combines macro/news/chart/supply-demand/valuation/risk factors.
- Ideas can be persisted in history with 3-month horizon and status.
- Existing single-symbol idea and backtest features remain accessible.
- Backend tests and frontend build/test pass or failures are documented with concrete blockers.
