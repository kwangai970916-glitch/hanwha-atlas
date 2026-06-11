# 한화 ATLAS — Agentic Investment Desk OS

> 바이브코딩 경진대회 · 주식운용 아이디어 부문 제출본 · (구 한화 PRISM)
> AI 에이전트가 시장을 읽고 **실제로 토론해서** 투자 아이디어를 발굴·심의하는 운용 데스크 OS.

> 📌 **심사 안내** — 라이브(서버) 버전은 실시간 데이터·LLM 구동에 **API 키가 필요**하며, 보안상 키는 저장소에 포함하지 않았습니다.
> **키 없이 바로 확인**하시려면 **오프라인 본 `index.html`을 더블클릭**해 주세요. 최근 실데이터가 내장되어 백엔드·설치 없이 전 기능이 동작합니다. 🙏

## ⚡ 2분 데모 경로 (심사위원용)

1. `index.html` 더블클릭 → 설치 없이 브라우저에서 열립니다 (오프라인 데모)
2. 상단 라이브 테이프에서 시세 흐름 확인
3. **[손익현황]** 탭 → 보유종목 행 클릭 → 우측 상세 Drawer
4. Drawer의 **"AI 위원회 소집"** 버튼 → AI투자위원회 탭으로 자동 이동 + 종목 자동 세팅 (원클릭 흐름)
5. **[AI 아이디어랩]** 탭 → "최근 결과" 클릭 → 11개 역할 에이전트의 5단계 토론 회의록·후보 종목 확인
6. **[시황에이전트]** 탭 → 장전/장중/마감 브리핑 확인

## 🎬 실행 방법 (2가지)

### 1) 오프라인 즉시 실행 — `index.html` 더블클릭 (서버 불필요)
- 최근 실데이터(시세·뉴스·섹터·PnL·위원회 결과)가 **HTML에 내장**되어 백엔드·설치·인터넷 없이 **전 탭·팝업·차트가 동작**합니다.
- 우상단 **"제출용 · 오프라인 모드"** 배지로 정적 데모임을 표시합니다.
- GitHub Pages를 켜면 이 `index.html`이 그대로 **온라인 데모 URL**이 됩니다.

### 2) 풀스택 실행 — 라이브 서버 (실시간 데이터 + 실제 LLM 토론)
```bash
# 백엔드 (FastAPI, Python 3.9)
cd backend && pip install -r requirements.txt
cp ../.env.example ../.env          # 키 입력(.env.example 참고)
uvicorn app.main:app --reload --port 8000
# 프런트엔드 (React + Vite)
cd frontend && npm install && npm run dev   # http://127.0.0.1:5173
```
> 🔑 키가 없어도 **규칙기반 폴백**으로 동작합니다. 키를 넣으면 실시간 시세 + 실제 멀티에이전트 LLM 토론이 활성화됩니다.

## 🧠 핵심 차별화 — 진짜 멀티에이전트 토론: 아이디에이션 위원회 (`backend/app/ideation/`)
"AI 회의" 연출이 아니라 **실제로 토론하는** 톱다운 발굴 엔진:
```
1. 사전조사·발굴   Macro PM + 발굴 스카우트 → 실시간 섹터·뉴스·6팩터로 후보풀 동적 발굴
2. 섹터 라운드테이블 Bull ↔ Bear 멀티라운드 왕복 → 리서치 매니저 판정
3. 종목 상정       스톡피커가 승리 레인에서 thesis 근거로 지명
4. 리스크 사전심의  공격·중립·보수 3-way 토론 → 리스크 매니저 보류 판정
5. PM 의장 최종선정  회의록 종합 → 숏리스트 랭킹 + 채택 근거·체크리스트
```
11 역할 · 실행당 ~14-18 LLM 호출 · 실시간 발언 스트리밍(LiveFeed) · 전 단계 규칙 폴백.

> ⚠️ AICommittee가 쓰는 벤더드 **TradingAgents(`committee_engine/`)** 는 자체 라이선스·대용량·키 포함이라 본 저장소에서 **제외**했습니다. 대신 벤더드 엔진이 없는 환경(서버 배포 등)에서는 **네이티브 위원회 엔진(`backend/app/committee_native.py`)** 이 동일한 산출물 계약(status/messages/decision)으로 in-process 구동되어 AICommittee 탭이 그대로 동작합니다. **오프라인 데모(`index.html`)에는 위원회 결과가 이미 내장**되어 있습니다.

## ☁️ 라이브 배포 (Vercel 프론트 + Railway 백엔드)

```
Vercel  ← frontend (빌드 환경변수 VITE_API_BASE=https://<railway-app>.up.railway.app)
Railway ← backend  (railway.toml 자동 인식, 환경변수 MIMO_API_KEY 필수)
```

1. **Railway**: 이 repo 연결 → `railway.toml`/루트 `requirements.txt`로 자동 빌드 → Variables에 `MIMO_API_KEY`(필수), `DART_API_KEY`(선택) 입력
2. **Vercel**: 이 repo 연결(`vercel.json`이 frontend 빌드) → Environment Variables에 `VITE_API_BASE=<Railway 공개 URL>` 입력
3. 배포 환경 동작: 손익현황은 mock 포트폴리오(`ATLAS_PNL_MOCK` 기본 ON), AI위원회는 네이티브 엔진, 나머지 탭은 로컬과 동일하게 실데이터로 동작합니다.

---

# 한화 PRISM — AI Investment Desk

**한화 PRISM** 은 한화손해보험의 주식 포트폴리오 운용을 위한 AI 통합 데스크입니다. (PRISM = **P**ortfolio · **R**isk · **I**nsight · **S**ignal · **M**arket) 시장 모니터링, 손익·위험 점검, 시황 브리핑, 아이디어 발굴/백테스트, 멀티에이전트 투자위원회를 하나의 화면(5탭)에서 연결합니다.

- 프론트: React 19 + Vite + Tailwind (한화 웜다크 터미널 테마)
- 백엔드: FastAPI (Python 3.9)
- AI 위원회: 격리된 venv(`committee_engine`, Python 3.13)에서 TradingAgents 멀티에이전트를 subprocess로 구동
- 위원회 LLM: Xiaomi MiMo V2.5 (`MIMO_API_KEY`)

> 본 자료는 내부 참고용 보조도구입니다. 표시되는 수치/리포트는 데이터 소스 상태에 따라 달라질 수 있으며, 최종 투자 의사결정은 담당 운용역의 판단에 따릅니다.

---

## 5개 탭 기능

### 1) 시장현황 (Live / Sector / Chart)
- KR 준실시간 시세 테이프: 네이버 금융 폴링 1차 + pykrx 폴백 (`/api/market/stream` SSE, 10초 주기)
- KPI 행: KOSPI · KOSDAQ(준실시간), USD/KRW · VIX · WTI · 금(yfinance) — `/api/market/kpi`
- 섹터 등락, 멀티에셋 시세 테이블, 지수/종목 캔들 차트(pykrx OHLCV)
- 시세 기준일(`price_as_of`)과 수집 시각(`fetched_at`)을 분리 표기

### 2) 손익현황 (P&L / Holdings / News)
- 인포맥스 마스터 엑셀(`Price_Raw(인포)` 시트)을 직독해 보유종목 평가/손익 집계 (`/api/pnl`)
- 손익 시계열 곡선: 포트 시작=100 리베이스 + BM 오버레이 (`/api/pnl/curve`)
- vs BM 위험지표: 연율수익/변동성/MDD/베타/추적오차(TE)/정보비율(IR)/초과수익 + 산식·관측치수 메타 (`/api/pnl/risk`)
- USD 표기 자산은 USDKRW 최신값으로 원화 환산, BM 미매핑 종목은 커버리지% 경고로 투명 표기
- 보유종목 행 클릭 → 우측 상세 Drawer → `AI 위원회 소집` 버튼으로 위원회 탭 원클릭 진입(영웅흐름)
- 보유종목 뉴스/공시 흐름(Google News RSS + 선택적 DART)

### 3) 시황에이전트 (장전 / 장중 / 장마감)
- 슬롯 선택(장전 07:00 / 장중 08:30 / 장마감 16:30 KST) 후 LLM 시황 리포트 생성 (`/api/briefing/{slot}`)
- 9개 섹션 인터랙티브 카드: title · stance · key_issue · bull_case · bear_case · macro_flow · kr_outlook · strategy · news_flow
- RS(상대강도) 4분면 산점도(KOSPI/KOSDAQ 토글), ADR 추이 라인, 등락 종목·섹터 바, 헤드라인
- 원본 PNG 리포트 미리보기/다운로드
- 발송 이력 레일(`/api/briefing/history`) + 다음 자동생성 카운트다운(`/api/briefing/schedule`)

### 4) 아이디어랩 (Backtest / AI)
- RAG 근거접지 AI 투자아이디어 (`/api/idea`): pykrx 시세·펀더멘털·수급·공매도 + Google News RSS + 선택적 DART 수집 후 MiMo LLM으로 생성. thesis/stance/목표가/핵심동인/리스크와 함께 evidence(근거-출처) 카드 제공. LLM 불가 시 결정적 폴백으로 graceful degrade
- 기관급 전략 백테스트 (`/api/backtest`), 전략 5종:
  - `ma_cross`(MA 5/20 크로스), `dual_momentum`(120일 절대모멘텀), `bollinger`(20·2σ 평균회귀), `breakout52`(52주 신고가 돌파), `vol_target`(목표변동성 15% + 추세필터)
  - CAGR/MDD/샤프/Sortino/Calmar/승률 + 자본곡선(전략 vs KOSPI) + 매매 마커 + 월별 히트맵
  - 거래비용·체결규칙(t+1 시가)·생존편향·면책 가정을 함께 노출

### 5) AI Committee (Multi-agent Review)
- 종목 입력 후 `위원회 소집` → 백엔드가 격리 venv의 `run_committee.py`를 subprocess로 실행 (`/api/committee/run` → `/status` → `/result`)
- TradingAgents 멀티에이전트(애널리스트 4 · Bull/Bear 리서처 + 리서치매니저 · 리스크 3 + 리스크매니저 · 트레이더/PM/의장) 심의 — UI는 4단계 14에이전트 파이프라인으로 진행 시각화
- 9개 리포트: 최종결정 · 투자위원회(investment_plan) · 투자토론(Bull/Bear) · 리스크토론 · 기술적 · 재무 · 뉴스 · 심리 · 트레이딩
- 한국 종목(종목명/6자리코드)·미국 티커 모두 지원. 한국 종목은 yfinance 티커로 정규화하고 뉴스는 한국어 Google News RSS 사용

---

## 아키텍처

```
브라우저 (React 19 / Vite / Tailwind, :5173)
        │  REST + SSE
        ▼
FastAPI 백엔드 (Python 3.9, uvicorn :8000)   backend/app/main.py
        │
        ├─ 시세      price_service(네이버+pykrx) · market_table(yfinance)
        ├─ 손익      pnl.py  ← 인포맥스 엑셀 직독 (openpyxl)
        ├─ 시황      briefing.py (+ backend/sitele 데이터 수집)
        ├─ 아이디어  idea_engine.py · backtest.py (pykrx)
        └─ 위원회    committee_runner.py
                         │ subprocess (격리)
                         ▼
       committee_engine/TradingAgents (Python 3.13 .venv)
         run_committee.py → TradingAgentsGraph (LLM=MiMo V2.5)
         결과: backend/data/committee_runs/<job>/decision.json
```

- 백엔드 기동 시 `committee_engine/TradingAgents/.env`를 수동 파싱해 키들을 `os.environ`에 주입(이미 설정된 값은 보존). 위원회 subprocess도 동일 `.env`를 로드합니다.
- 위원회는 의도적으로 별도 venv로 분리되어 있어, 백엔드(3.9)와 langchain/langgraph 등 무거운 의존성이 섞이지 않습니다.

---

## 데이터 소스

| 소스 | 용도 | 인증 |
| --- | --- | --- |
| 네이버 금융 | KR 지수/종목 준실시간 시세(1차) | 불필요 |
| pykrx | 시세 폴백, OHLCV 캔들, 백테스트, 종목명↔코드 | 불필요 |
| yfinance | USD/KRW · VIX · WTI · 금 · 멀티에셋 테이블, 위원회 가격/지표/재무 | 불필요 |
| Google News RSS | 보유종목·시황·아이디어·위원회 뉴스 | 불필요 |
| 인포맥스 마스터 엑셀 | 보유종목/손익/위험지표 기준 시세(`Price_Raw(인포)`, `BM_RAW(인포)`, `자산마스터`, `현재보유`, `매도내역`) | 파일 |
| Xiaomi MiMo V2.5 | 위원회·시황·아이디어 LLM | `MIMO_API_KEY` (필수) |
| DART (OpenDartReader) | 보유종목 공시, 아이디어 보강 | `DART_API_KEY` (선택) |
| ECOS (한국은행) | 거시지표 보강 | `ECOS_API_KEY` (선택) |

엑셀 파일 위치: `backend/data/주간주식시황_V10_마스터파일.xlsx` (없으면 손익 탭은 명시적 에러를 반환합니다.)

---

## 실행 방법 (Windows / PowerShell)

### 0) 키 설정 (필수: MIMO)
위원회/시황/아이디어 LLM은 `committee_engine/TradingAgents/.env`의 `MIMO_API_KEY`를 사용합니다. 백엔드가 기동 시 이 `.env`를 읽어 환경변수로 주입합니다.

```
# C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/committee_engine/TradingAgents/.env
MIMO_API_KEY=...            # 필수
DART_API_KEY=...            # 선택 (공시)
ECOS_API_KEY=...            # 선택 (거시)
```

### 1) 백엔드 (FastAPI, Python 3.9)

```powershell
Set-Location "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/backend"
$env:PYTHONPATH = (Get-Location).Path
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2) 위원회 격리 venv (Python 3.13) — 최초 1회 점검
이미 구성되어 있습니다. 동작만 확인하려면:

```powershell
& "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/committee_engine/TradingAgents/.venv/Scripts/python.exe" --version
# Python 3.13.x
```

### 3) 프론트엔드 (React 19 + Vite)

```powershell
Set-Location "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/frontend"
npm install
npm run dev
```

브라우저에서 `http://127.0.0.1:5173` 접속. (프론트는 `VITE_API_BASE` 미설정 시 `http://127.0.0.1:8000`을 호출합니다.)

---

## 스모크 테스트

핵심 엔드포인트 6종(KPI · 손익 · 시세 스냅샷 · 위원회 기동 · 시세 테이블 · 위원회 seed 파일)을 FastAPI TestClient로 빠르게 점검합니다. 위원회 라이브 완주(수 분)는 기다리지 않고 `job_id` 즉시 반환만 확인합니다.

```powershell
Set-Location "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/backend"
$env:PYTHONPATH = (Get-Location).Path
python scripts/smoke.py
```

모든 항목 PASS 면 종료코드 0, 하나라도 FAIL 이면 1.

### 단위 테스트

```powershell
# Backend (Python 3.9)
Set-Location "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/backend"
$env:PYTHONPATH = (Get-Location).Path
python -m pytest tests -q

# Frontend
Set-Location "C:/Users/infomax/Desktop/Jinkwang/03.AI/바이브코딩_경진대회_주식운용아이디어/ai-investment-desk-os/frontend"
npm test -- --run
npm run build
```

---

## 주요 API

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/api/health` | 헬스체크 |
| GET | `/api/market/kpi` | KOSPI/KOSDAQ/USDKRW/VIX/WTI/금 KPI |
| GET | `/api/market/stream` | KR 준실시간 시세 SSE |
| GET | `/api/market/table` · `/sectors` · `/candles/{symbol}` | 시세 테이블·섹터·캔들 |
| GET | `/api/pnl` · `/api/pnl/curve` · `/api/pnl/risk` · `/api/pnl/news` | 손익·곡선·위험지표·뉴스 |
| POST/GET | `/api/briefing/{slot}` · `/{slot}/status` · `/{slot}/png` | 시황 생성·상태·PNG |
| GET | `/api/briefing/history` · `/schedule` | 발송 이력·스케줄 카운트다운 |
| POST | `/api/idea` · `/api/backtest` | RAG 아이디어·백테스트 |
| POST/GET | `/api/committee/run` · `/status` · `/result` | 위원회 기동·상태·결과 |

---

## 컴플라이언스

본 자료는 내부 참고용으로, 투자 판단의 보조자료입니다. AI가 생성한 시황·아이디어·위원회 리포트는 데이터 소스 상태와 LLM 비결정성에 따라 달라질 수 있으며, 과거 백테스트 성과가 미래 수익을 보장하지 않습니다. 최종 투자 의사결정과 책임은 담당 운용역의 판단에 따릅니다.
