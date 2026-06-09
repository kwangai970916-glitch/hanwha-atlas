# 시황에이전트(Briefing Agent) 전면 개편 — 설계서

- 작성일: 2026-06-02
- 대상: `ai-investment-desk-os` 시황에이전트 탭(장전/장중/장마감)
- 상태: 설계 승인 완료(사용자), 구현 계획 대기

## 1. 배경 / 문제

현재 시황 브리핑은 단일 `SYSTEM_PROMPT`(음슴체, 고정 9섹션)를 세 슬롯(장전/장중/장마감)에 공통 적용하고, 슬롯별로 **입력 데이터만** 다르게 넣는다. 그 결과:

- 슬롯 간 내용·깊이·톤이 사실상 동일해 차별화가 없다.
- 프론트는 9섹션 고정 카드(`SectionCards`)로 렌더 — 슬롯 성격을 반영 못 함.
- PNG는 9섹션 키 기반 단일 템플릿 → 깊이/가독성 부족.

## 2. 목표

슬롯마다 **페르소나·구조·깊이**를 차별화하되, 앱 화면과 PNG는 **통일된 시각 언어**를 유지한다.

- 장전 = **한지영** 위원 스타일: 매크로/글로벌 톱다운 → 국내 영향, 컨센서스 괴리 중심, 정중·분석 서술체
- 장마감 = **강진혁** 위원 스타일: 주체별 수급·섹터·종목 마감총평 + 내일 관전포인트, 간결 임팩트체
- 장중 = **기존 "아침시황"**(텔레 리포트) 이식: KOSPI/KOSDAQ 섹터 주도 테마 내러티브 + RS·섹터·ADR·등락·뉴스 데이터
- 음슴체 강제 해제 → 페르소나별 자연 서술체

## 3. 비범위 (Out of scope)

- 새 데이터 소스 추가 없음(기존 `auto_data_fetcher`/`interactive` 데이터 재사용).
- 텔레그램 발송 로직 변경 없음.
- LLM 공급자 교체 없음(아래 4.4 유지).

## 4. 설계

### 4.1 슬롯 공통 envelope (데이터 모델)

`generate_report_sections(slot, market_data)` 의 반환을 **슬롯 불문 동일한 봉투**로 통일한다. 슬롯 차이는 `blocks` 내용으로만 표현 → "통일 템플릿" 충족.

```jsonc
{
  "slot": "premarket | intraday | close",
  "persona": "한지영 | 강진혁 | 아침시황",
  "title": "주도변수·시장반응·판단",
  "stance": "RISK-ON | NEUTRAL | RISK-OFF",
  "headline": "핵심 요약 2~3줄(히어로 콜아웃)",
  "blocks": [
    {
      "id": "global_kr",
      "label": "글로벌 마감 → 국내 영향",
      "type": "bullets | paragraph | kv",
      "body": ["...", "..."]            // bullets: string[], paragraph: string, kv: [{k,v,tone?}]
    }
  ],
  "as_of": "ISO8601",
  "legacy": { /* 4.5 PNG 호환용 9키 매핑 */ }
}
```

블록 `type`:
- `bullets` — `body: string[]` (불릿 리스트)
- `paragraph` — `body: string` (서술 문단)
- `kv` — `body: [{k, v, tone?: 'up'|'down'|'neutral'}]` (지표 키-값, 매크로 패널용)

### 4.2 슬롯별 블록 구성

**장전 / premarket / 한지영** (정중·분석 서술체)
1. `global_kr` 글로벌 마감 → 국내 영향 — 인과체인(미증시·금리·환율·원자재 → 국내 시초) · paragraph
2. `key3` 오늘의 핵심 포인트 3 — 컨센서스 대비 괴리 · bullets(3)
3. `macro` 매크로·금리·환율 — VIX·F&G·미10년물·DXY·원달러 · kv
4. `sector_strategy` 주목 섹터·전략 — 톱다운 도출 섹터/테마 + 포지션 방향 · bullets
5. `checkpoint` 운용 체크포인트 — 오늘 일정/이벤트 + 관찰변수 · bullets

**장마감 / close / 강진혁** (간결 임팩트체)
1. `wrap` 마감 총평 — 지수 결과 + 그날 장 성격 · paragraph
2. `flows` 주체별 수급 — 외국인/기관/개인 현·선물 · kv
3. `sectors` 주도·부진 섹터 — 오른/빠진 섹터 + 이유 · bullets
4. `movers` 특징주 — 상승/하락 TOP + 테마 · bullets
5. `tomorrow` 내일 관전 포인트 — 미선물·내일 일정·관찰변수 · bullets

**장중 / intraday / 아침시황** (KOSPI·KOSDAQ 테마 내러티브)
1. `kospi_theme` KOSPI 흐름·주도 테마 · paragraph
2. `kosdaq_theme` KOSDAQ 흐름·주도 테마 · paragraph
3. `sector_rs` 섹터·RS 동향 — RS 4분면/섹터 등락 해석 · bullets
4. `breadth_flow` 등락·수급 — 등락종목수·무버·외/기 · kv
5. `headlines` 주요 헤드라인 — 뉴스→테마 연결 · bullets

### 4.3 백엔드 변경 (`backend/sitele/hanwha_report_text.py` 중심)

- 단일 `SYSTEM_PROMPT` → **3개 페르소나 시스템 프롬프트**: `PROMPT_PREMARKET_HANJIYOUNG`, `PROMPT_CLOSE_KANGJINHYUK`, `PROMPT_INTRADAY_MORNING`. 각 프롬프트가 4.2 블록 스키마(JSON envelope)를 출력하도록 지시. 음슴체 규칙 제거, 페르소나 톤 명시.
- 슬롯별 user-prompt 빌더(`_build_*_prompt`)는 유지하되 **envelope 출력 형식**으로 변경.
- `_parse_sections`/`_postprocess_sections`를 envelope 스키마에 맞게 갱신(필수 키·블록 id 검증, 지수 레벨 sanitize는 해당 블록에만 적용).
- `_fallback_sections(slot)` 도 슬롯별 블록 구조의 graceful 폴백 반환.

### 4.4 LLM 경로 (유지)

`ANTHROPIC_API_KEY` → `anthropic` SDK(`claude-sonnet-4-6`) → 실패 시 Codex CLI(OAuth) → 내장 fallback. 긴 한국어 내러티브 품질을 위해 현행 유지.

### 4.5 PNG 재설계 (슬롯별 기존 템플릿 재디자인 · 슬롯맞춤 가변 분량)

- **장전/장마감**: `hanwha_report_template.html` + `hanwha_report_renderer.py`를 재디자인 → envelope 블록을 렌더하는 **1페이지 페르소나 리포트**(헤더 persona·title·stance / headline / 블록 그리드 / 핵심 데이터). 한화 웜다크 테마.
- **장중(아침시황)**: 기존 **3페이지 텔레 템플릿**(`report_template_tele.html` + `report_renderer_tele.py`)을 유지·개선. Page1=테마 내러티브(envelope blocks → `analysis_text` 조립), Page2=KOSPI(차트·RS·섹터·헤드라인), Page3=KOSDAQ. 캔들은 기존 `generate_candle_tele.py` 재사용.
- **호환 매핑**: envelope에 `legacy`(title/stance/key_issue/bull_case/bear_case/macro_flow/kr_outlook/strategy/news_flow) best-effort 매핑을 함께 emit → 재디자인 전까지 기존 렌더러가 깨지지 않게 함(점진 이행 안전망).
- **다중 PNG**: 장중은 `png_paths`(page1~3) 리스트, 장전/장마감은 단일 `png_path`. `run_*.py`와 `briefing.py`가 이를 결과에 담아 반환.

### 4.6 프론트 변경 (`frontend/src/components/briefing/*`)

- `SectionCards`(9 고정) → **`BriefingReport` 블록 렌더러**: envelope 기반, `block.type`별(bullets/paragraph/kv) 렌더, 아이콘·웜다크 카드 그리드.
- 헤더: **persona 배지 + stance 컬러 pill + headline 콜아웃** + 생성 시각.
- 데이터비주(`RsQuadrantCard`/`AdrCard`/`MoversCard`/`BriefingNewsCard`) 재활용. **장중은 KOSPI/KOSDAQ 토글** 지원.
- `PngCard`: 단일 png + **다중 png 갤러리**(장중 page1~3) 지원.
- 슬롯 탭·생성·폴링·이력 레일 골격은 유지. `BriefingAgent.tsx`의 `result.sections` 소비 → `result.report`(envelope)로 전환.

### 4.7 briefing.py 연동

`run_briefing(slot)`이 캡처하는 산출물을 `sections`(9키) → `report`(envelope)로 전환. 하위호환을 위해 `legacy`도 함께 노출. PNG는 `png_path`/`png_paths` 모두 채움. `_summarize_decision`은 envelope(title/stance) 기반으로 갱신.

## 5. 컴포넌트 경계 (요약)

| 단위 | 책임 | 입력 | 출력 |
| --- | --- | --- | --- |
| 페르소나 프롬프트 3종 | 슬롯별 톤·구조 정의 | market_data | envelope JSON(LLM) |
| `generate_report_sections` | LLM 호출·파싱·후처리·폴백 | slot, market_data | envelope dict |
| `hanwha_report_renderer`(재디자인) | 장전/장마감 1p PNG | envelope | png_path |
| `report_renderer_tele`(개선) | 장중 3p PNG | envelope+데이터 | png_paths[] |
| `BriefingReport`(신규) | 블록 렌더 | envelope | React UI |
| `BriefingAgent` | 오케스트레이션 | apiBase | 탭/생성/렌더 |

## 6. 테스트 전략

- 백엔드 단위:
  - envelope 스키마 검증(슬롯별 blocks id/개수, stance 유효값, title 보정).
  - `legacy` 9키 매핑 존재.
  - LLM 미가용 시 슬롯별 fallback envelope 반환(공백 금지).
- 프론트:
  - `BriefingReport` block.type별 렌더(bullets/paragraph/kv) 스냅샷/존재 검증.
  - `tsc --noEmit` 클린, 기존 vitest 그린 유지.
- 통합(수동): 세 슬롯 생성 → 화면 블록 + 데이터비주 + PNG(장중 3p) 확인.

## 7. 리스크 / 완화

- **LLM 비결정성**: postprocess 정규화 + 슬롯별 fallback envelope로 방어.
- **PNG 파이프라인 회귀**: `legacy` 매핑을 항상 emit하여 재디자인 이행 중에도 기존 렌더 동작 보장. 렌더러 교체는 슬롯별로 점진 적용.
- **장중 다중 PNG**: 프론트 `PngCard` 갤러리 + `briefing.py` `png_paths` 처리. 단일 png 슬롯과 분기.
- **uvicorn --reload Windows 불안정**: 백엔드 변경 후 수동 재시작 절차 유지.

## 8. 구현 순서(개략)

1. `hanwha_report_text.py`: envelope 스키마 + 3 페르소나 프롬프트 + 슬롯 빌더/파서/폴백/`legacy` 매핑.
2. `run_intraday.py` market_data 보강(KOSDAQ·무버·RS) + 장중 텔레 렌더 연결.
3. `briefing.py`: `report`/`png_paths` 캡처·반환.
4. 프론트 `BriefingReport` + `PngCard` 갤러리 + `BriefingAgent` 연동 + 장중 KOSPI/KOSDAQ 토글.
5. PNG 템플릿 재디자인(장전·장마감 hanwha 1p / 장중 tele 3p).
6. 테스트(백엔드 스키마·폴백, 프론트 렌더, tsc) + 수동 통합 확인.
