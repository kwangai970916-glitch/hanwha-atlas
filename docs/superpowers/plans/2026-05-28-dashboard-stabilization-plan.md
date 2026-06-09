# Dashboard Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 경진대회 시연용 AI Investment Desk OS를 탭별로 안정적으로 실행되고 수정 가능한 상태로 만든다.

**Architecture:** 현재 구조는 FastAPI backend + React/Vite frontend + 별도 시황텔레 자동화 코드가 결합된 MVP다. 우선 테스트/실행 안정성을 확보하고, 그 다음 API 응답 표준화와 탭별 UX/데모 완성도를 개선한다.

**Tech Stack:** FastAPI, Pydantic, pytest, React, TypeScript, Vite, Vitest, Testing Library, pykrx, yfinance, OpenDartReader, Anthropic API, Windows PowerShell.

---

## 진단 요약

### 확인된 강점
- `backend/app/main.py`에 시장, P&L, 브리핑, 백테스트, 아이디어 생성, 종목 분석 API가 이미 구현되어 있다.
- `frontend/src/App.tsx`에 시장현황/손익현황/시황에이전트/아이디어랩 4개 탭이 연결되어 있다.
- `backend/app/evaluation.py`, `backend/app/security_analysis.py`는 단순 LLM wrapper가 아니라 구조화된 평가 엔진 형태다.
- `시황텔레/` 및 `backend/sitele/` 리포트 생성 자산이 있어서 PNG 리포트 데모까지 가능하다.
- `npm run build`는 성공한다.

### 핵심 미비점
1. 테스트 안정성 미흡
   - Frontend Vitest가 `EventSource is not defined`로 전부 실패한다.
   - Backend 전체 테스트는 외부 의존/시간 문제로 빠르게 통과하지 못할 가능성이 있다.
2. 데모 안정성 미흡
   - pykrx/yfinance/OpenDart/Anthropic/Codex/텔레그램 등 외부 의존이 많다.
   - API key나 네트워크가 없으면 일부 탭이 비어 보일 수 있다.
3. API 응답 형태 혼재
   - 일부는 `wrap()` 표준 응답, 일부는 raw dict다.
   - 프론트가 API별로 다르게 처리해야 해서 확장성이 떨어진다.
4. 코드 중복
   - 루트 `시황텔레/`와 `backend/sitele/`가 유사 기능을 중복 보유한다.
5. 탭별 완성도 편차
   - 시장현황은 스트리밍이 있으나 fallback/로딩/오류 표시가 약하다.
   - 손익현황은 보유종목 파일 의존성이 높다.
   - 시황에이전트는 생성 시간이 길고 상태/실패 UX가 단순하다.
   - 아이디어랩은 Anthropic key가 없으면 사실상 비어 보인다.
6. 운영 설정 미흡
   - CORS가 전체 허용이다.
   - `.env.example`은 있으나 데모 모드/운영 모드 구분이 명확하지 않다.

---

## File Structure

### 수정 대상
- `frontend/src/setupTests.ts`
  - Vitest용 `EventSource`, `ResizeObserver`, `fetch` mock 보강.
- `frontend/src/App.tsx`
  - SSE 실패 시 `/api/market/snapshot` fallback 추가.
- `frontend/src/api.ts`
  - API helper와 표준 에러 처리 확장.
- `frontend/src/components/MarketDashboard.tsx`
  - 데이터 없음/지연/외부 데이터 상태 표시.
- `frontend/src/components/PnlDashboard.tsx`
  - 손익 데이터 없음 fallback과 오류 UX 개선.
- `frontend/src/components/BriefingAgent.tsx`
  - 생성 상태, 마지막 산출물, 실패 사유 표시 개선.
- `frontend/src/components/IdeaLab.tsx`
  - Anthropic key 미설정 시 샘플 아이디어 fallback 렌더링.
- `backend/tests/conftest.py`
  - backend 테스트 PYTHONPATH 및 외부 API mock fixture 정리.
- `backend/app/main.py`
  - 외부 의존 API fallback 강화, raw response에 `mode/as_of/error` 일관 필드 추가.
- `backend/app/services.py`
  - 샘플-first demo mode 명시.
- `backend/app/briefing.py`
  - 시황 리포트 생성 실패 시 샘플 PNG/상태 응답 fallback.
- `README.md`
  - Windows 실행, 테스트, 데모 모드 설명 업데이트.

### 신규 생성 후보
- `backend/app/demo_data.py`
  - 외부 API 실패 시 사용할 데모 데이터 공통 모듈.
- `frontend/src/types.ts`
  - API 공통 타입 분리.
- `docs/superpowers/plans/2026-05-28-dashboard-stabilization-plan.md`
  - 본 계획 문서.

---

## Task 1: Frontend 테스트 안정화

**Files:**
- Modify: `frontend/src/setupTests.ts`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: EventSource mock 추가**

`frontend/src/setupTests.ts`를 다음 형태로 확장한다.

```ts
import '@testing-library/jest-dom'

class MockEventSource {
  url: string
  onmessage: ((event: MessageEvent) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  readyState = 1

  constructor(url: string) {
    this.url = url
  }

  close() {
    this.readyState = 2
  }
}

Object.defineProperty(globalThis, 'EventSource', {
  writable: true,
  value: MockEventSource,
})

Object.defineProperty(globalThis, 'ResizeObserver', {
  writable: true,
  value: class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
})
```

- [ ] **Step 2: 테스트 실행**

Run:

```powershell
cd frontend
npm test -- --run
```

Expected:
- 기존 `ReferenceError: EventSource is not defined`는 사라진다.
- 남는 실패가 있으면 각 실패 메시지 기준으로 fetch mock 또는 텍스트 assertion을 조정한다.

- [ ] **Step 3: 빌드 재확인**

Run:

```powershell
cd frontend
npm run build
```

Expected:
- `✓ built` 출력.

---

## Task 2: Backend 테스트 실행 안정화

**Files:**
- Create: `backend/tests/conftest.py`
- Test: `backend/tests/*.py`

- [ ] **Step 1: PYTHONPATH 자동 설정 conftest 추가**

`backend/tests/conftest.py` 생성:

```python
from __future__ import annotations

import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
```

- [ ] **Step 2: 빠른 테스트 실행**

Run:

```powershell
python -m pytest backend/tests/test_api.py backend/tests/test_evaluation.py -q
```

Expected:
- ImportError 없이 테스트 실행.

- [ ] **Step 3: 외부 의존 테스트 분리**

전체 테스트 중 pykrx/yfinance/OpenDart 네트워크 호출이 발생하는 테스트는 mock을 사용하도록 조정한다. 우선 실패 테스트명을 기록한다.

Run:

```powershell
python -m pytest backend/tests -q --tb=short
```

Expected:
- 60초 안에 결과 확인 가능.

---

## Task 3: 데모 모드/fallback 데이터 공통화

**Files:**
- Create: `backend/app/demo_data.py`
- Modify: `backend/app/main.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: demo data module 생성**

`backend/app/demo_data.py` 생성:

```python
from __future__ import annotations

import datetime as dt


def demo_market_ticks() -> dict:
    return {
        "ticks": [
            {"symbol": "^KS11", "display": "KOSPI", "price": 2725.31, "change": 0.72, "asset_type": "index"},
            {"symbol": "^KQ11", "display": "KOSDAQ", "price": 873.22, "change": 0.41, "asset_type": "index"},
            {"symbol": "005930", "display": "삼성전자", "price": 78500, "change": 1.16, "asset_type": "stock", "sector": "반도체"},
            {"symbol": "000660", "display": "SK하이닉스", "price": 204000, "change": 2.31, "asset_type": "stock", "sector": "반도체"},
            {"symbol": "012450", "display": "한화에어로", "price": 228500, "change": -0.43, "asset_type": "stock", "sector": "방산"},
        ],
        "breadth": {"advancers": 3, "decliners": 1, "new_highs": 1},
        "as_of": dt.datetime.now().isoformat(),
        "transport": "demo-fallback",
    }
```

- [ ] **Step 2: `_fetch_pykrx_ticks()` fallback 교체**

`backend/app/main.py`에서 예외 발생 시 빈 배열 대신 `demo_market_ticks()` 반환.

```python
except Exception as e:
    from .demo_data import demo_market_ticks
    data = demo_market_ticks()
    data["error"] = str(e)
    return data
```

- [ ] **Step 3: API 테스트 추가**

`backend/tests/test_api.py`에 fallback contract 테스트 추가:

```python
def test_market_snapshot_returns_ticks_even_when_provider_fails(monkeypatch):
    from app import main

    def fail_provider():
        raise RuntimeError("provider down")

    monkeypatch.setattr(main, "_fetch_pykrx_ticks", fail_provider)
    client = TestClient(main.app)
    response = client.get("/api/market/snapshot")
    assert response.status_code == 200
```

위 테스트는 실제 구현 방식에 맞게 monkeypatch 대상을 조정한다.

---

## Task 4: 시장현황 탭 UX 안정화

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/MarketDashboard.tsx`
- Test: `frontend/src/App.test.tsx`

- [ ] **Step 1: SSE fallback 추가**

`frontend/src/App.tsx`의 `useEffect`에서 `EventSource` 미지원/에러 시 snapshot fetch로 대체한다.

핵심 로직:

```ts
const applyMarketData = (d: any) => {
  setTicks((d.ticks ?? []).map((t: any) => ({
    symbol: t.symbol,
    display: t.display ?? t.symbol,
    price: t.price,
    value: t.price,
    change: t.change,
    asset_type: t.asset_type ?? 'index',
    sector: t.sector,
  })))
}
```

- [ ] **Step 2: 빈 데이터 안내 추가**

`MarketDashboard.tsx`에 ticks가 없을 때 다음 메시지 표시:

```tsx
<div className="bg-card border border-border rounded-xl p-4 text-sm text-muted">
  실시간 데이터 연결 전입니다. 데모 데이터 또는 마지막 스냅샷을 불러오는 중입니다.
</div>
```

- [ ] **Step 3: 테스트**

Run:

```powershell
cd frontend
npm test -- --run src/App.test.tsx
```

Expected:
- 시장현황 탭 렌더링 테스트 통과.

---

## Task 5: 손익현황 탭 fallback 강화

**Files:**
- Modify: `backend/app/pnl.py`
- Modify: `frontend/src/components/PnlDashboard.tsx`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 보유종목 파일 미존재 시 샘플 반환**

`backend/app/pnl.py`에서 CSV/Excel 미존재 시 `data/samples/sample_portfolio.csv`를 우선 사용하고, 그것도 실패하면 명시적 demo holdings를 반환한다.

- [ ] **Step 2: Frontend 오류 카드 개선**

`PnlDashboard.tsx`에서 `data.error`가 있어도 holdings가 있으면 화면은 보여주고 상단에 경고만 표시한다.

```tsx
{data.error && (
  <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-3 text-sm text-yellow-200">
    일부 실시간 데이터가 샘플/캐시로 대체되었습니다: {data.error}
  </div>
)}
```

- [ ] **Step 3: 테스트**

Run:

```powershell
python -m pytest backend/tests/test_api.py -q
cd frontend
npm test -- --run
```

---

## Task 6: 시황에이전트 탭 데모 안정화

**Files:**
- Modify: `backend/app/briefing.py`
- Modify: `frontend/src/components/BriefingAgent.tsx`

- [ ] **Step 1: 실패 상태 표준화**

`run_briefing(slot)`은 항상 다음 중 하나를 반환하도록 맞춘다.

```python
{"status": "done", "success": True, "png_path": "...", "slot": slot}
{"status": "error", "success": False, "error": "...", "slot": slot}
```

- [ ] **Step 2: Frontend polling 간격 단축/상태 표시**

`BriefingAgent.tsx`에서 5초 polling을 1초 또는 2초로 줄이고, 진행 메시지를 표시한다.

```tsx
{status === 'running' && (
  <div className="bg-card border border-border rounded-xl p-4 text-sm text-muted">
    {slot} 리포트를 생성 중입니다. 외부 데이터 연결이 느리면 샘플 데이터로 대체됩니다.
  </div>
)}
```

- [ ] **Step 3: 수동 검증**

Run:

```powershell
cd backend
$env:PYTHONPATH=(Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 터미널:

```powershell
cd frontend
npm run dev
```

Browser:
- `http://127.0.0.1:5173`
- 시황에이전트 탭 클릭
- 장마감 선택 후 지금 생성
- 성공/실패 메시지가 명확히 보여야 한다.

---

## Task 7: 아이디어랩 fallback/상품성 개선

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/src/components/IdeaLab.tsx`

- [ ] **Step 1: Anthropic key 미설정 fallback 반환**

`/api/idea`에서 API key가 없을 때 `result: null` 대신 샘플 아이디어를 반환한다.

```python
if not api_key:
    return {
        "result": {
            "thesis": "반도체 업황 회복과 HBM 수요 확대를 바탕으로 삼성전자 이익 추정치 상향 가능성을 점검합니다.",
            "bull_case": "메모리 가격 반등, 서버 AI 투자 확대, 외국인 수급 개선이 동시에 확인될 경우 리레이팅 가능성이 있습니다.",
            "bear_case": "가격 반등 지연, 환율 변동, 경쟁사 공급 확대 시 이익 모멘텀이 둔화될 수 있습니다.",
            "target_price": "데모 기준 12개월 95,000원",
            "stop_loss": "종가 기준 72,000원 이탈 시 재검토",
            "horizon": "3~12개월",
        },
        "mode": "demo-fallback",
    }
```

- [ ] **Step 2: Frontend mode 배지 표시**

`IdeaLab.tsx`에서 응답의 `mode`가 `demo-fallback`이면 샘플 아이디어라는 배지를 표시한다.

---

## Task 8: API 응답 표준화 1차

**Files:**
- Modify: `backend/app/main.py`
- Modify: `frontend/src/api.ts`

- [ ] **Step 1: 모든 raw dict에 최소 공통 필드 추가**

대상:
- `/api/market/snapshot`
- `/api/market/sectors`
- `/api/market/candles/{symbol}`
- `/api/market/table`
- `/api/pnl`
- `/api/pnl/news`
- `/api/backtest`
- `/api/idea`

최소 필드:

```json
{
  "as_of": "ISO timestamp",
  "mode": "live|demo-fallback|sample|error-fallback",
  "error": null
}
```

- [ ] **Step 2: 프론트 fetch helper 작성**

`frontend/src/api.ts`에 공통 helper 추가:

```ts
export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${await response.text()}`)
  }
  return response.json() as Promise<T>
}
```

---

## Task 9: 중복 시황텔레 모듈 정리 계획만 수립

**Files:**
- Inspect only: `시황텔레/*.py`
- Inspect only: `ai-investment-desk-os/backend/sitele/*.py`
- Create: `docs/sitele-integration-notes.md`

- [ ] **Step 1: 파일별 차이 비교**

Run:

```powershell
Compare-Object (Get-Content ..\시황텔레\run_close.py) (Get-Content backend\sitele\run_close.py)
```

- [ ] **Step 2: 통합 원칙 문서화**

`docs/sitele-integration-notes.md`에 다음을 기록한다.

```markdown
# Sitele Integration Notes

## Source of truth
- 루트 `시황텔레/`를 원본 자동화 모듈로 둔다.
- backend는 import wrapper만 보유한다.

## Short-term
- 경진대회 전에는 기능 안정화를 우선하고 대규모 이동은 하지 않는다.

## Long-term
- 공통 패키지 `sitele_core`로 분리한다.
```

---

## Task 10: README 데모 실행 문서 정리

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Windows 실행 순서 업데이트**

README에 다음 블록 추가:

```markdown
## 데모 모드 실행 순서

### Backend
```powershell
cd ai-investment-desk-os\backend
$env:PYTHONPATH = (Get-Location).Path
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### Frontend
```powershell
cd ai-investment-desk-os\frontend
npm install
npm run dev
```

접속: http://127.0.0.1:5173
```

- [ ] **Step 2: 테스트 명령 업데이트**

```markdown
### Backend Test
```powershell
cd ai-investment-desk-os
python -m pytest backend/tests -q
```

### Frontend Test
```powershell
cd ai-investment-desk-os\frontend
npm test -- --run
npm run build
```
```

---

## 실행 우선순위

### P0: 오늘 바로 해야 할 것
1. Frontend `EventSource` 테스트 mock 추가.
2. Backend 테스트 `conftest.py` 추가.
3. 시장 데이터/아이디어 생성 fallback 추가.
4. 대시보드 로컬 실행 확인.

### P1: 탭별 수정 전 해야 할 것
1. 시장현황 탭 빈 데이터 UX.
2. 손익현황 탭 파일/가격 fallback.
3. 시황에이전트 상태 UX.
4. 아이디어랩 demo fallback 배지.

### P2: 구조 개선
1. API 응답 표준화.
2. 시황텔레 중복 통합 방향 문서화.
3. 운영/데모 모드 환경변수 분리.

---

## Verification Commands

```powershell
cd C:\Users\infomax\Desktop\Jinkwang\03.AI\바이브코딩_경진대회_주식운용아이디어\ai-investment-desk-os
python -m pytest backend/tests/test_api.py backend/tests/test_evaluation.py -q
cd frontend
npm test -- --run
npm run build
```

Expected:
- Backend selected tests pass.
- Frontend tests pass or only documented API-text assertion failures remain.
- Build succeeds.

---

## Self-review

- Spec coverage: 사용자의 요구인 “미비점 진단 + 계획”을 테스트, 데모 안정성, 탭별 UX, API 구조, 중복 코드, 문서화로 나누어 커버했다.
- Placeholder scan: 실행 가능한 파일 경로와 코드 예시를 포함했다.
- Type consistency: Frontend는 `ticks`, `mode`, `error`, `as_of` 중심으로 통일했다.
- Repository status: 현재 `ai-investment-desk-os`는 git repository가 아니므로 commit 단계는 생략한다. git 초기화/연결 후에는 Task 단위 commit을 권장한다.
