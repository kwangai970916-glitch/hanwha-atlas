# ai_committee/ — DEPRECATED (구 결정론 위원회)

상태: **DEPRECATED / 비활성 (frontend·라이브 파이프라인 미사용)**

## 무엇인가
이 패키지는 결정론(if/else 규칙 기반) "AI 위원회"의 구버전 구현이다.
8개 에이전트(Fundamental / Valuation / Technical / Sentiment / Macro /
Risk Manager / Bear Case / Insurance PM)가 샘플 데이터(`data/samples`)와
`security_analysis` 컨텍스트를 입력받아 규칙 기반 의견·메모를 합성했다.

## 왜 deprecated 인가
실제 LLM 기반 다중에이전트 위원회는 신규 모듈
**`app/committee_runner.py`** (외부 TradingAgents 엔진 + MiMo LLM,
`committee_engine/TradingAgents`)로 전면 대체되었다.
현재 프론트엔드(`frontend/src/components/AICommittee.tsx`)와
운영 API는 다음 라이브 엔드포인트만 사용한다:

- `POST /api/committee/run`
- `GET  /api/committee/status`
- `GET  /api/committee/result`

`app/main.py` 는 이 패키지(`app.ai_committee`)를 **import 하지 않는다.**

## 그럼 왜 폴더를 지우거나 옮기지 않았나
`backend/tests/test_ai_committee.py` 가 아직 이 패키지의
`app.ai_committee.agents.*` 모듈을 직접 import 하여 검증한다.
폴더를 rename/삭제하면 해당 테스트의 import 가 깨져 회귀가 발생하므로,
보수적으로 **현 위치를 유지하고 본 README 로 deprecated 를 명시**한다.

## 신규 작업 지침
- 새로운 위원회 기능은 반드시 `app/committee_runner.py` 경로를 사용할 것.
- 이 패키지에 신규 의존성을 추가하지 말 것.
- 테스트 정리 시점에 `test_ai_committee.py` 와 함께 묶어 제거를 검토할 것.
