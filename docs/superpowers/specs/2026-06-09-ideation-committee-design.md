# 아이디에이션 위원회 (Ideation Committee) 설계

> 작성일: 2026-06-09
> 목표: IdeaLab의 "AI 아이디에이션 회의"를 **연출(UI 메타포)**에서 **실제 멀티에이전트 토론 엔진**으로 승격.
> AICommittee(TradingAgents)와 동급 깊이를, 그러나 "단일 종목 분석"이 아닌 **"톱다운 발굴(discovery)"** 임무로 차별화.

## 0. 배경 — 현재 무엇이 가짜인가

- 프론트 `IdeaLab.tsx`는 "AI 서브에이전트 회의 / 뉴스 큐레이터·Bull·Bear·PM 의장"을 4단계 카드로 보여주지만, 백엔드에 **대응하는 에이전트가 없다.**
- `idea_radar.py:475`의 `_build_committee_minutes`는 코드 주석으로 명시: *"These are not simulated live chat messages; they summarize the actual radar output."* → 즉 **정적 요약**.
- 진행 애니메이션은 `IdeaLab.tsx:209-215`의 `setInterval`(5초마다 단계 증가) — **타이머 연출**.
- 실제 LLM 호출은 `build_radar()` 1회전당 **최대 6회**(매크로 서술 1 + 픽 보강 5)뿐. **토론 라운드 없음.**

대조: AICommittee는 LangGraph 멀티에이전트 그래프를 **별도 subprocess**로 돌려 14 에이전트가 각자 LLM 호출, Bull↔Bear / 3-way 리스크 **실제 왕복 토론**, 실행당 ~15-20+ LLM 호출, `messages.jsonl`로 실시간 스트리밍.

## 1. 확정된 제품 결정 (브레인스토밍 결과)

| 항목 | 결정 |
|---|---|
| 핵심 임무 | **톱다운 발굴 토론** — 에이전트가 시장을 놓고 토론해 투자 후보를 "발굴". AICommittee(단일종목 심층)와 차별화 |
| 깊이·속도 | **풀뎀·멀티라운드 (수 분)** — 실제 다라운드 왕복, 실시간 피드 스트리밍 |
| 후보 유니버스 | **동적 발굴** — 실시간 섹터·뉴스·스크리너에서 테마/종목 추출. `THEME_SEEDS`는 폴백으로만 |
| 기존 radar | **위원회 1단계로 흡수** — radar 룰엔진을 Macro/Sector 사전조사 grounding으로 재사용 |
| 실행 기반 | **B. 인프로세스 오케스트레이터** — 백그라운드 스레드 + committee와 동일 파일 스트리밍 계약 |
| 리스크 토론 | **3-way (공격·중립·보수)** — AICommittee 완전 동급 |
| 결과 스키마 | **RadarResponse 상위호환** — 기존 리치 UI 최대 재사용, `committee_minutes`만 실제 transcript로 교체 |

## 2. 아키텍처 개요

신규 패키지 `backend/app/ideation/` (각 파일 단일책임, ~300줄 이하):

| 파일 | 책임 | 핵심 재사용 |
|---|---|---|
| `runner.py` | job 관리(start/status/messages/result/latest), 데몬 스레드 기동, 워치독 | `committee_runner.py` 패턴 (subprocess → **스레드**) |
| `stream.py` | `messages.jsonl` 한 줄 append(idx 단조증가), `status.json` 갱신, `decision.json` 기록 | committee 스트리밍 계약 |
| `discovery.py` | **동적 유니버스 발굴** — 섹터랭크 + 뉴스플로우 + 6팩터 스코어 → 후보풀 (+ seed 폴백) | `idea_radar._build_sector_rank`, `idea_radar._build_live_factor_maps`, `idea_engine._collect_*` |
| `agents.py` | 에이전트 정의: (name, stage, icon, system_prompt, grounding 수집 + 호출) | `idea_engine._call_llm`, `idea_engine.build_idea` |
| `orchestrator.py` | 단계+토론 라운드 제어("그래프"), 각 발언 emit, 결과 조립 | `idea_radar._build_market_regime` (1단계 grounding) |

radar(`idea_radar.py`)·idea_engine은 **삭제하지 않고 import**해 흡수. subprocess/venv 불필요(전부 `backend.app` 내부 모듈).

### 2.1 LLM 호출 계약

- 1차 경로: 기존 `idea_engine._call_llm(system, user) -> (parsed_dict|None, provider|None, errors[])` 재사용. 에이전트는 **구조화 JSON**을 반환하도록 프롬프트.
  - 각 에이전트 JSON 스키마는 `speech`(자연어 발언, LiveFeed 표시용) + 단계별 구조화 필드(예: `winning_lanes`, `nominations`, `blocked_symbols`, `ranked`)를 함께 담는다 → 표시 텍스트와 기계 가용 결정을 동시에 확보.
- 보조 경로: 자유 서술이 더 나은 곳을 위해 `agents._speak_text(system, user) -> str` 얇은 헬퍼 추가(동일 provider 폴백 체인, `_extract_json` 생략, 원문 반환). 필요 최소한으로만 사용.
- provider 체인은 기존 그대로: **MiMo V2.5 → OpenAI(gpt-4o-mini) → Anthropic(claude-sonnet-4-6)**. 키 없거나 파싱 실패 시 **룰기반 폴백 발언**으로 graceful degrade.

## 3. 에이전트 토폴로지 (11 역할 · LLM 토론 참여 9, 풀 멀티라운드)

> 11 역할 = Macro PM, 발굴 스카우트(룰기반·LLM 0), Bull·Bear 리서처, 리서치 매니저, 스톡피커, 공격·보수·중립 심의역, 리스크 매니저, PM 의장.

LLM 호출 예산: 1단계 1 + 2단계 (Bull+Bear)×N라운드+매니저 ≈ 3-5 + 3단계 후보별 build_idea ≈ 5(병렬) + 4단계 3-way×라운드+매니저 ≈ 4-6 + 5단계 1 ≈ **총 14-18회**. → "수 분" 깊이.

### 1단계 — 사전조사·발굴 `discovery`
- **Macro PM**(매크로 전략가): `idea_radar._build_market_regime`로 실데이터 국면 판정(VIX·USD/KRW·지수 + 테마 분산) + LLM 서술 1회. 발언 emit.
- **발굴 스카우트**(Discovery Scout): `discovery.py` — 실시간 섹터랭크(auto_data_fetcher) + 뉴스플로우(`data_loader.load_news` + `idea_engine._collect_news`) + 6팩터 스코어 → **동적 후보풀**. 룰기반(LLM 0). 라이브 실패 시 `THEME_SEEDS` 폴백. 발언 emit(발굴된 레인/종목 수 요약).

### 2단계 — 섹터 라운드테이블 `sector_debate` (실제 왕복 토론)
- **Bull 리서처**: 어느 섹터 레인이 유망한지 주장(섹터 스코어·뉴스·매크로 grounding).
- **Bear 리서처**: 과열·리스크 레인 반박. **Bull의 직전 발언을 입력으로 받아** 반박(왕복).
- N라운드 반복(`max_sector_rounds`, 기본 2 → 4발언). `should_continue_debate` 류 카운터로 종료 제어.
- **리서치 매니저**: 양측 종합 → **유망 레인(winning_lanes) 판정**. 발언 emit.

### 3단계 — 종목 상정 `nomination`
- **스톡피커**: winning_lanes 안에서 구체 종목 지명. 후보별 `idea_engine.build_idea(symbol)`로 thesis/why_now/evidence grounding. 레인별 **병렬**(ThreadPoolExecutor). 각 지명 발언 emit.

### 4단계 — 리스크 사전심의 `risk_review` (3-way 토론)
- **공격적 심의역**(Risky): 모멘텀·상방 강조.
- **보수적 심의역**(Safe/Conservative): 과열·추격매수·하방 강조. RSI·MA20 타이밍(`idea_radar._compute_timing_signal`)·공매도·변동성 grounding.
- **중립 심의역**(Neutral): 균형 판정.
- 3-way 라운드로빈(`max_risk_rounds`, 기본 1 → 3발언). 카운터 종료.
- **리스크 매니저**: 종합 → 각 후보 통과/보류(blocked_symbols)·경고 emit.

### 5단계 — PM 의장 최종선정 `decision`
- **PM 의장**: 전 단계 회의록 종합 → 숏리스트 **top5 랭킹** + 종목별 채택근거·`why_now`·`counter_evidence`·`checklist`. 최종 발언 emit → `decision.json` 조립.

## 4. 스트리밍 계약 (AICommittee와 동일 스키마)

출력 디렉터리: `backend/data/idea_committee_runs/{job_id}/`

### 4.1 `messages.jsonl` (append-only, 라이브 피드)
```json
{"idx": 0, "ts": "2026-06-09T10:00:00", "agent": "Macro PM", "stage": "discovery", "text": "VIX 16.2로 변동성 안정...", "icon": "activity"}
```
- 필드·의미는 committee와 동일(`idx, ts, agent, stage, text, icon`). `text`는 240자 내 발췌.

### 4.2 `status.json` (단계 전이마다 덮어쓰기)
```json
{"stage": "sector_debate", "stage_label": "섹터 라운드테이블 토론 중", "step": 2, "keywords": "AI 반도체", "ts": "..."}
```
- stage enum: `starting → discovery → sector_debate → nomination → risk_review → decision → done`(+`error`).
- `STAGE_META`: 각 stage → (step 0-5, 한국어 label).

### 4.3 `decision.json` (완료 시, **RadarResponse 상위호환**)
기존 `IdeaLab.tsx`가 읽는 필드를 그대로 채워 **기존 UI 무수정 동작**:
```jsonc
{
  "generated_at": "...", "horizon_months": 3, "keywords": "...", "engine": "ideation_committee",
  "market_regime": { /* radar 호환 */ }, "macro_flow": { ... },
  "sector_flow": [ /* 토론 결과 winning_lanes 반영 */ ],
  "themes": [ ... ],
  "top_picks": [ /* PM 랭킹: thesis/why_now/evidence/factor_scores/timing_signal/counter_evidence/checklist */ ],
  "stock_candidates": [ /* top_picks 미러 (프론트 호환) */ ],
  "news_flow": [ ... ],
  "committee_minutes": [ /* ★ 정적요약 → 실제 에이전트 transcript (agent/stage/text/source/icon) */ ],
  "transcript": [ /* messages.jsonl 전체 순서 보존 (리플레이용) */ ],
  "pipeline": { "summary": "...", "stages": ["Macro","Sector","Stock"] },
  "data_quality": { "mode": "live|fallback", "regime_source": "...", "warnings": [...] }
}
```

### 4.4 Job API (`backend/app/main.py`)
| 라우트 | 메서드 | 핸들러 |
|---|---|---|
| `/api/idea/committee/run?keywords=&horizon_months=` | POST | `ideation.runner.start_run` → `{job_id}` |
| `/api/idea/committee/status?job_id=` | GET | `get_status` (status.json + job_id) |
| `/api/idea/committee/messages/{job_id}?since=` | GET | `get_messages` (`{messages, total}`, idx≥since) |
| `/api/idea/committee/result?job_id=` | GET | `get_result` (decision.json) |
| `/api/idea/committee/latest` | GET | `get_latest_result` (최근 done + **seed 폴백**) |

기존 `/api/idea/radar`는 **유지**(빠른 룰 결과가 필요한 위젯/홈용). 위원회는 신규 엔드포인트.

## 5. 프론트 (IdeaLab.tsx) 변경

- "회의 시작" → `/api/idea/committee/run` POST 후 `status`/`messages` **실제 폴링**(AICommittee `run()` 패턴 이식: status 5초, messages 2초, `since` 증분).
- 4단계 진행카드: `setInterval` 타이머(209-215) **제거** → 실제 `status.stage`로 `STAGE_TO_PHASE` 매핑 구동.
- **LiveFeed 공용화**: `AICommittee.tsx:655`의 `LiveFeed`를 `components/committee/LiveFeed.tsx`로 추출해 양쪽 재사용. 에이전트 발언 실시간 표시.
- 완료 시 `decision.json`을 기존 `PipelineOverview / CommitteeMinutes / SectorFlowBoard / CandidateBoard / CandidateDecisionReport`에 그대로 주입(상위호환이라 무수정). `committee_minutes`가 실제 transcript가 되어 회의록이 진짜가 됨.
- 에러: `ErrorState` + stderr/trace 상세(AICommittee 패턴).

## 6. 데모 안전성 / Graceful Degrade

- **단계별 폴백**: 라이브 데이터 실패 → `THEME_SEEDS`; LLM 실패/무키 → 룰기반 발언. 엔진은 **절대 hard-fail 없이** 항상 랭킹 숏리스트 산출.
- **seed 런 캐시**: `idea_committee_runs/seed/*.json`(known-good decision.json) → `/latest`가 seed 폴백(committee `samsung.json` 전략과 동일)으로 데모 중 빈 화면 방지.
- **타임아웃/워치독**: 에이전트별 타임아웃(LLM 네트워크) + 전체 워치독(기본 600s) → 초과 시 부분결과로 `done` 또는 `error` 기록.
- **idempotent 스트림 쓰기**: idx 카운터는 스레드 단일 소유(orchestrator), append-only.

## 7. 테스트

- **단위**
  - `discovery`: 라이브 비었을 때 `THEME_SEEDS` 폴백, 후보풀 dedup, 6팩터 스코어 범위.
  - `stream`: idx 단조증가, jsonl 1줄=1메시지, status 전이 순서, decision.json 스키마 유효.
  - 랭킹/분류: PM 랭킹 결정론(동률 처리), counter_evidence/checklist 비어있지 않음.
- **통합**
  - `_call_llm`(+`_speak_text`) mock → 오케스트레이터 1회전: 전 단계 messages.jsonl 채워짐, decision.json에 랭킹후보+transcript, **모든 폴백 경로**(라이브 무·LLM 무) 검증.
  - 결정론 모드(mock/use_llm=false): 기존 radar 테스트 방식 답습 → 안정 스냅샷.
- **프론트**: `IdeaLab.test.tsx` 신규 폴링 플로우(run→status→messages→result fetch mock), LiveFeed 렌더, 타이머 제거 회귀.

## 8. 비범위 (YAGNI)

- LangGraph 도입(직접 오케스트레이션으로 충분), subprocess 격리(인프로세스로 결정).
- 종목별 풀 딥다이브(그건 AICommittee 소관 — "위원회 소집"으로 핸드오프하는 기존 `actions:['committee']` 링크 유지).
- 실시간 WebSocket(폴링으로 충분, 기존 패턴 일치).

## 9. 작업 단위 (구현 순서 개요)

1. `ideation/stream.py` + 스키마 + 단위테스트 (계약 먼저).
2. `ideation/discovery.py` (radar 재사용 + seed 폴백) + 테스트.
3. `ideation/agents.py` (프롬프트·grounding·`_speak_text`) + LLM mock 테스트.
4. `ideation/orchestrator.py` (5단계·토론 라운드·emit·조립) + 통합테스트.
5. `ideation/runner.py` (스레드 job·워치독·seed/latest) + 테스트.
6. `main.py` 엔드포인트 5종.
7. 프론트: LiveFeed 추출 → IdeaLab 폴링 전환 → 타이머 제거 → 결과 주입.
8. seed 런 생성·캐시, 데모 리허설.
