# Idea Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved AI Idea Radar + Research Note Pipeline inside Idea Lab.

**Architecture:** Add a deterministic backend radar service with JSON-file history persistence, expose thin FastAPI endpoints, then render a frontend workbench above the existing single-symbol idea/backtest tools. The radar uses a multi-factor Discovery + Conviction gate so RS is never the only reason for a pick.

**Tech Stack:** FastAPI/Python 3.9, JSON file storage, React 19 + TypeScript + Vite + Tailwind, Vitest/Testing Library, pytest/FastAPI TestClient.

---

## File Structure

- Create `backend/app/idea_radar.py`: deterministic radar generation, factor scoring, history CRUD.
- Modify `backend/app/main.py`: add `/api/idea/radar` and `/api/idea/history` endpoints.
- Create `backend/tests/test_idea_radar.py`: API and persistence coverage.
- Modify `frontend/src/components/IdeaLab.tsx`: add radar workbench UI, API calls, history display, save/status actions while preserving existing idea/backtest sections.
- Create `frontend/src/components/IdeaLab.test.tsx`: frontend rendering and mocked API coverage.

## Task 1: Backend Radar Service

**Files:**
- Create: `backend/app/idea_radar.py`
- Test: `backend/tests/test_idea_radar.py`

- [ ] **Step 1: Write failing tests**

```python
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app import idea_radar

client = TestClient(app)

def test_radar_returns_composite_top_five():
    response = client.get('/api/idea/radar')
    assert response.status_code == 200
    body = response.json()
    assert body['horizon_months'] == 3
    assert len(body['themes']) >= 3
    assert len(body['top_picks']) == 5
    pick = body['top_picks'][0]
    assert {'chart', 'supply_demand', 'news', 'macro', 'valuation', 'risk'} <= set(pick['factor_scores'])
    assert len(pick['evidence']) >= 4
    assert not all('RS' in item['title'] for item in pick['evidence'])

def test_history_save_list_update_with_temp_store(tmp_path, monkeypatch):
    monkeypatch.setattr(idea_radar, 'HISTORY_PATH', tmp_path / 'idea_history.json')
    pick = client.get('/api/idea/radar').json()['top_picks'][0]
    saved = client.post('/api/idea/history', json={'pick': pick, 'note': '검토'}).json()
    assert saved['status'] == 'new'
    assert saved['horizon_months'] == 3
    listed = client.get('/api/idea/history').json()
    assert len(listed['items']) == 1
    updated = client.patch(f"/api/idea/history/{saved['idea_id']}", json={'status': 'reviewing', 'note': '회의 상정'}).json()
    assert updated['status'] == 'reviewing'
    assert updated['note'] == '회의 상정'
```

- [ ] **Step 2: Run tests to verify failure**

Run: `cd backend; $env:PYTHONPATH=(Get-Location).Path; python -m pytest tests/test_idea_radar.py -q`
Expected: FAIL because endpoints/module do not exist.

- [ ] **Step 3: Implement service**

Create `backend/app/idea_radar.py` with deterministic fallback themes, multi-factor scoring, `build_radar`, `list_history`, `save_history`, and `update_history`.

- [ ] **Step 4: Run tests**

Run: `cd backend; $env:PYTHONPATH=(Get-Location).Path; python -m pytest tests/test_idea_radar.py -q`
Expected: PASS.

## Task 2: FastAPI Endpoints

**Files:**
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_idea_radar.py`

- [ ] **Step 1: Add endpoint imports and handlers**

Add handlers near existing `/api/idea` endpoints:

```python
@app.get('/api/idea/radar')
def idea_radar_endpoint(keywords: str = '', horizon_months: int = 3):
    from .idea_radar import build_radar
    return build_radar(keywords=keywords, horizon_months=horizon_months)

@app.get('/api/idea/history')
def idea_history_endpoint():
    from .idea_radar import list_history
    return {'items': list_history()}

@app.post('/api/idea/history')
async def save_idea_history(request: Request):
    from .idea_radar import save_history
    payload = await request.json()
    return save_history(payload.get('pick') or payload, note=payload.get('note', ''))

@app.patch('/api/idea/history/{idea_id}')
async def update_idea_history_endpoint(idea_id: str, request: Request):
    from .idea_radar import update_history
    payload = await request.json()
    return update_history(idea_id, status=payload.get('status'), note=payload.get('note'))
```

- [ ] **Step 2: Run backend tests**

Run: `cd backend; $env:PYTHONPATH=(Get-Location).Path; python -m pytest tests/test_idea_radar.py tests/test_idea_api.py -q`
Expected: PASS.

## Task 3: Frontend Radar Workbench

**Files:**
- Modify: `frontend/src/components/IdeaLab.tsx`
- Create: `frontend/src/components/IdeaLab.test.tsx`

- [ ] **Step 1: Write frontend tests**

Mock `/api/idea/radar` and `/api/idea/history`, render `IdeaLab`, and assert text: `AI Idea Radar`, `Market Regime`, `Theme Radar`, `Top Picks`, `Idea History`, and five cards.

- [ ] **Step 2: Run tests to verify failure**

Run: `cd frontend; npm test -- --run src/components/IdeaLab.test.tsx`
Expected: FAIL before UI exists.

- [ ] **Step 3: Add TypeScript types and state**

Add `RadarResponse`, `RadarTheme`, `RadarPick`, and `IdeaHistoryItem` types plus `radarState`, `radar`, `history`, `radarError`, and save/update handlers.

- [ ] **Step 4: Render new workbench above existing sections**

Add a top card with controls, market regime, theme radar, Top Picks 5 research-note cards, and history. Keep existing AI 투자아이디어 and 전략 백테스팅 cards below.

- [ ] **Step 5: Run frontend tests/build**

Run: `cd frontend; npm test -- --run src/components/IdeaLab.test.tsx; npm run build`
Expected: PASS.

## Task 4: Full Verification

**Files:**
- All modified files

- [ ] **Step 1: Run backend focused tests**

Run: `cd backend; $env:PYTHONPATH=(Get-Location).Path; python -m pytest tests/test_idea_radar.py tests/test_idea_api.py -q`
Expected: PASS.

- [ ] **Step 2: Run frontend focused tests/build**

Run: `cd frontend; npm test -- --run src/components/IdeaLab.test.tsx; npm run build`
Expected: PASS.

- [ ] **Step 3: Manual acceptance check**

Confirm current files prove:
- `/api/idea/radar` returns five Top Picks.
- Top Picks include multi-factor evidence and counter-evidence.
- `/api/idea/history` saves and updates 3-month ideas.
- IdeaLab displays the new radar and retains old idea/backtest tools.
