# 아이디에이션 위원회 (Ideation Committee) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** IdeaLab의 "AI 아이디에이션 회의"를 UI 연출에서 실제 멀티에이전트 톱다운 발굴 토론 엔진으로 승격한다.

**Architecture:** 신규 `backend/app/ideation/` 패키지에 인프로세스 백그라운드-스레드 오케스트레이터를 구현한다. radar 룰엔진(`idea_radar.build_radar`)을 1단계 grounding으로 흡수하고, `idea_engine._call_llm`(MiMo→OpenAI→Anthropic)로 5단계 11역할(Bull/Bear 섹터 토론, 3-way 리스크 토론, PM 종합)을 돌린다. AICommittee와 동일한 `messages.jsonl`/`status.json`/`decision.json` 파일 스트리밍 계약 + job API를 노출하고, 결과는 RadarResponse 상위호환으로 정형해 기존 IdeaLab UI를 재사용한다.

**Tech Stack:** Python 3.9 / FastAPI / pytest(+TestClient) / ThreadPoolExecutor / React+TS(Vite, framer-motion) / pykrx·yfinance(기존 수집기 재사용).

---

## 환경 주의

- **이 워크스페이스는 git 저장소가 아니다.** 각 Task 끝의 **Checkpoint**는 "관련 테스트 그린 = 체크포인트"를 의미한다. `git init`을 했다면 제시된 `git commit` 명령을 실제 실행하고, 아니면 그린 테스트로 갈음한다.
- 테스트는 `backend/`에서 실행한다(`backend/tests/conftest.py`가 `sys.path`에 backend 루트를 추가 → `from app...` import 가능). 명령은 모두 `cd backend` 기준.
- 라이브 데이터/LLM은 항상 best-effort. 어떤 단계도 hard-fail 없이 폴백한다(테스트는 mock/룰모드로 결정론 확보).

## 파일 구조 (생성/수정)

| 파일 | 책임 |
|---|---|
| `backend/app/ideation/__init__.py` | 패키지 마커 |
| `backend/app/ideation/stream.py` | `RunStream`: messages.jsonl(idx 단조) / status.json / decision.json 기록 + `STAGE_META` |
| `backend/app/ideation/discovery.py` | `discover_universe()`: radar 룰모드 흡수 → 국면·레인·후보풀(+seed 폴백) |
| `backend/app/ideation/agents.py` | `_speak_json`/`_speak_text` + 11역할 발언 함수(프롬프트·grounding·룰폴백) |
| `backend/app/ideation/orchestrator.py` | `run_committee()`: 5단계·토론 라운드 제어·emit·`assemble_decision()` |
| `backend/app/ideation/runner.py` | 스레드 job 관리(start/status/messages/result/latest)·워치독·seed 폴백 |
| `backend/app/main.py` (수정) | `/api/idea/committee/*` 5개 엔드포인트 |
| `backend/tests/test_ideation_*.py` | 단위·통합 테스트(flat 컨벤션) |
| `frontend/src/components/committee/LiveFeed.tsx` | AICommittee LiveFeed 추출(공용) |
| `frontend/src/components/AICommittee.tsx` (수정) | 추출된 LiveFeed import |
| `frontend/src/components/IdeaLab.tsx` (수정) | radar 동기호출 → 위원회 비동기 폴링, 타이머 제거 |

---

## Task 1: 스트리밍 계약 (`stream.py`)

**Files:**
- Create: `backend/app/ideation/__init__.py`
- Create: `backend/app/ideation/stream.py`
- Test: `backend/tests/test_ideation_stream.py`

- [ ] **Step 1: 빈 패키지 마커 생성**

`backend/app/ideation/__init__.py`:
```python
# ideation: 실제 멀티에이전트 아이디에이션 위원회 엔진
```

- [ ] **Step 2: 실패 테스트 작성**

`backend/tests/test_ideation_stream.py`:
```python
from __future__ import annotations
import json
from app.ideation.stream import RunStream, STAGE_META


def test_emit_writes_monotonic_jsonl(tmp_path):
    s = RunStream(tmp_path)
    s.emit('Macro PM', 'discovery', 'VIX 16.2 안정', icon='activity')
    s.emit('Bull 리서처', 'sector_debate', '반도체 레인 유망' * 40)  # 길이 초과
    lines = (tmp_path / 'messages.jsonl').read_text(encoding='utf-8').strip().splitlines()
    assert len(lines) == 2
    m0, m1 = json.loads(lines[0]), json.loads(lines[1])
    assert m0['idx'] == 0 and m1['idx'] == 1
    assert m0['agent'] == 'Macro PM' and m0['stage'] == 'discovery' and m0['icon'] == 'activity'
    assert len(m1['text']) <= 240  # 240자 절단
    assert 'ts' in m0


def test_set_stage_writes_status_with_label_and_step(tmp_path):
    s = RunStream(tmp_path)
    s.set_stage('sector_debate', keywords='AI 반도체')
    st = json.loads((tmp_path / 'status.json').read_text(encoding='utf-8'))
    assert st['stage'] == 'sector_debate'
    assert st['step'] == STAGE_META['sector_debate'][0]
    assert st['stage_label'] == STAGE_META['sector_debate'][1]
    assert st['keywords'] == 'AI 반도체'


def test_write_decision_roundtrip(tmp_path):
    s = RunStream(tmp_path)
    s.write_decision({'engine': 'ideation_committee', 'top_picks': []})
    d = json.loads((tmp_path / 'decision.json').read_text(encoding='utf-8'))
    assert d['engine'] == 'ideation_committee'
```

- [ ] **Step 3: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_stream.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ideation.stream'`

- [ ] **Step 4: 구현**

`backend/app/ideation/stream.py`:
```python
from __future__ import annotations
import datetime as dt
import json
from pathlib import Path
from typing import Any, Dict

KST = dt.timezone(dt.timedelta(hours=9))

# stage -> (step 0-5, 한국어 label). 프론트 4단계 진행카드/STAGE_TO_PHASE와 매핑.
STAGE_META: Dict[str, tuple] = {
    'starting':      (0, '시작 중'),
    'discovery':     (1, '사전조사·발굴 중'),
    'sector_debate': (2, '섹터 라운드테이블 토론 중'),
    'nomination':    (3, '종목 상정 중'),
    'risk_review':   (4, '리스크 사전심의 중'),
    'decision':      (5, 'PM 의장 최종선정 중'),
    'done':          (5, '회의 완료'),
    'error':         (0, '오류 발생'),
}


def iso_now() -> str:
    return dt.datetime.now(KST).isoformat(timespec='seconds')


class RunStream:
    """단일 job의 messages.jsonl / status.json / decision.json 기록기.

    orchestrator 스레드가 단독 소유한다(동시 쓰기 없음). idx는 emit마다 단조 증가.
    """

    def __init__(self, out_dir: Path | str):
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._idx = 0
        self._msg_path = self.out_dir / 'messages.jsonl'
        self._status_path = self.out_dir / 'status.json'
        self._decision_path = self.out_dir / 'decision.json'

    @property
    def idx(self) -> int:
        return self._idx

    def emit(self, agent: str, stage: str, text: str, icon: str = 'message') -> None:
        msg = {
            'idx': self._idx, 'ts': iso_now(), 'agent': agent, 'stage': stage,
            'text': (text or '').strip()[:240], 'icon': icon,
        }
        with self._msg_path.open('a', encoding='utf-8') as f:
            f.write(json.dumps(msg, ensure_ascii=False) + '\n')
        self._idx += 1

    def set_stage(self, stage: str, **extra: Any) -> None:
        step, label = STAGE_META.get(stage, (0, stage))
        payload = {'stage': stage, 'stage_label': label, 'step': step, 'ts': iso_now()}
        payload.update(extra)
        self._status_path.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')

    def write_decision(self, decision: Dict[str, Any]) -> None:
        self._decision_path.write_text(
            json.dumps(decision, ensure_ascii=False, indent=2), encoding='utf-8')
```

- [ ] **Step 5: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_stream.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Checkpoint**

```bash
git add backend/app/ideation/__init__.py backend/app/ideation/stream.py backend/tests/test_ideation_stream.py
git commit -m "feat(ideation): streaming contract (messages/status/decision)"
```

---

## Task 2: 동적 유니버스 발굴 (`discovery.py`)

radar 룰엔진을 1단계 grounding으로 흡수한다. `build_radar`를 **LLM 없이 라이브 팩터 모드**로 호출해 국면·섹터레인·후보풀을 얻고, 위원회가 토론할 구조로 reshape한다. 라이브 실패 시 radar 자체가 `THEME_SEEDS`로 graceful degrade하므로 별도 폴백 분기는 source 태깅만 한다.

**Files:**
- Create: `backend/app/ideation/discovery.py`
- Test: `backend/tests/test_ideation_discovery.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_discovery.py`:
```python
from __future__ import annotations
from app.ideation import discovery


def test_discover_universe_shape_rule_mode():
    # use_llm 경로를 타지 않도록 라이브/LLM 없이도 동작해야 한다(폴백 결정론).
    u = discovery.discover_universe('AI 반도체', horizon_months=3)
    assert set(u) >= {'regime', 'themes', 'candidates', 'sector_flow', 'news_flow', 'source'}
    assert isinstance(u['candidates'], list) and len(u['candidates']) >= 1
    c = u['candidates'][0]
    assert {'symbol', 'name', 'sector', 'theme', 'score', 'factor_scores'} <= set(c)
    assert u['source'] in {'live', 'seed'}
    assert isinstance(u['regime'], dict) and 'label' in u['regime']


def test_lanes_in_themes_have_sector():
    u = discovery.discover_universe('', horizon_months=3)
    assert all('sector' in t for t in u['themes'])
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ideation.discovery'`

- [ ] **Step 3: 구현**

`backend/app/ideation/discovery.py`:
```python
from __future__ import annotations
from typing import Any, Dict, List


def discover_universe(keywords: str, horizon_months: int = 3) -> Dict[str, Any]:
    """radar 룰엔진을 흡수해 위원회 1단계 grounding을 만든다.

    use_llm=False(결정론·빠름) + use_live_factors=True(가능 시 실데이터). 라이브 실패는
    radar 내부에서 THEME_SEEDS로 graceful degrade된다. 반환은 토론용으로 reshape.
    """
    from .. import idea_radar as ir
    try:
        radar = ir.build_radar(
            keywords=keywords, horizon_months=horizon_months,
            use_llm=False, use_live_factors=True, enrich_top_picks=False,
        )
    except Exception:
        # 최후 폴백: 라이브/팩터 전부 끈 순수 시드
        radar = ir.build_radar(keywords=keywords, horizon_months=horizon_months,
                               use_llm=False, use_live_factors=False, enrich_top_picks=False)

    mode = (radar.get('data_quality') or {}).get('mode', '')
    source = 'live' if mode == 'live_factors' else 'seed'

    candidates: List[Dict[str, Any]] = radar.get('stock_candidates') or radar.get('top_picks') or []
    return {
        'regime': radar.get('market_regime') or {},
        'themes': radar.get('themes') or [],
        'candidates': candidates,
        'sector_flow': radar.get('sector_flow') or [],
        'news_flow': radar.get('news_flow') or [],
        'sector_rank': radar.get('sector_rank') or [],
        'source': source,
        '_radar': radar,  # assemble_decision에서 RadarResponse 상위호환 베이스로 재사용
    }
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_discovery.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint**

```bash
git add backend/app/ideation/discovery.py backend/tests/test_ideation_discovery.py
git commit -m "feat(ideation): dynamic universe discovery via radar absorption"
```

---

## Task 3: LLM 발언 헬퍼 (`agents.py` 1/2 — 토대)

`_call_llm`(JSON 반환)을 래핑해 (parsed|fallback, provider) 튜플을 주는 `_speak_json`과, 자유 서술용 원문 반환 `_speak_text`를 만든다. 둘 다 키 없음/예외 시 룰 폴백.

**Files:**
- Create: `backend/app/ideation/agents.py`
- Test: `backend/tests/test_ideation_agents_core.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_agents_core.py`:
```python
from __future__ import annotations
from app.ideation import agents


def test_speak_json_uses_fallback_when_llm_unavailable(monkeypatch):
    # _call_llm이 (None, None, errors) → 폴백 반환
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['no_llm_key']))
    parsed, provider = agents._speak_json('sys', 'user', fallback={'speech': 'fb', 'x': 1})
    assert parsed == {'speech': 'fb', 'x': 1}
    assert provider == 'rules'


def test_speak_json_returns_llm_dict(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm',
                        lambda s, u: ({'speech': 'real', 'favored_lanes': ['반도체']}, 'mimo', []))
    parsed, provider = agents._speak_json('sys', 'user', fallback={'speech': 'fb'})
    assert parsed['favored_lanes'] == ['반도체']
    assert provider == 'mimo'


def test_speak_text_falls_back(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    text, provider = agents._speak_text('sys', 'user', fallback_text='규칙 발언')
    assert text == '규칙 발언' and provider == 'rules'
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_agents_core.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ideation.agents'`

- [ ] **Step 3: 구현 (헬퍼만)**

`backend/app/ideation/agents.py`:
```python
from __future__ import annotations
import json
from typing import Any, Dict, List, Optional, Tuple


def _speak_json(system: str, user: str, fallback: Dict[str, Any]) -> Tuple[Dict[str, Any], str]:
    """_call_llm(JSON 반환) 래퍼. 성공 시 (parsed, provider), 실패 시 (fallback, 'rules')."""
    try:
        from ..idea_engine import _call_llm
        parsed, provider, _errs = _call_llm(system, user)
        if isinstance(parsed, dict) and parsed:
            return parsed, (provider or 'llm')
    except Exception:
        pass
    return fallback, 'rules'


def _speak_text(system: str, user: str, fallback_text: str) -> Tuple[str, str]:
    """자유 서술용. _call_llm은 JSON을 기대하므로, system에 {"speech": ...} 한 줄 스키마를 강제하고
    speech 필드만 뽑아 원문처럼 쓴다. 실패 시 fallback_text."""
    schema_hint = system + ' 응답은 {"speech": "<한국어 2~3문장>"} JSON 하나만 출력한다.'
    parsed, provider = _speak_json(schema_hint, user, fallback={'speech': fallback_text})
    speech = str(parsed.get('speech') or fallback_text).strip()
    return (speech or fallback_text), provider


def _fmt(obj: Any) -> str:
    """프롬프트에 안전하게 실데이터를 직렬화."""
    try:
        return json.dumps(obj, ensure_ascii=False)[:2000]
    except Exception:
        return str(obj)[:2000]
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_agents_core.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Checkpoint**

```bash
git add backend/app/ideation/agents.py backend/tests/test_ideation_agents_core.py
git commit -m "feat(ideation): LLM speak helpers with rule fallback"
```

---

## Task 4: 토론 에이전트 (`agents.py` 2/2 — 11역할)

각 역할은 grounding(실데이터)을 받아 발언(speech) + 구조화 결정을 반환한다. 모든 함수는 LLM 무가용 시 결정론 룰 폴백을 갖는다.

**Files:**
- Modify: `backend/app/ideation/agents.py` (append)
- Test: `backend/tests/test_ideation_agents_roles.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_agents_roles.py`:
```python
from __future__ import annotations
from app.ideation import agents

REGIME = {'label': 'Selective risk-on', 'summary': '위험선호 우호', 'data_basis': ['VIX 16.2 안정']}
LANES = [
    {'sector': '반도체', 'theme': 'AI 인프라', 'score': 82, 'news_score': 80, 'macro_tags': ['AI capex']},
    {'sector': '방산', 'theme': '방산·우주', 'score': 70, 'news_score': 74, 'macro_tags': ['지정학']},
]
CANDS = [
    {'symbol': '000660', 'name': 'SK하이닉스', 'sector': '반도체', 'theme': 'AI 인프라', 'score': 86,
     'factor_scores': {'chart': 86, 'news': 87, 'risk': 63}},
]


def test_macro_brief_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    speech, regime = agents.macro_brief(REGIME)
    assert isinstance(speech, str) and speech
    assert regime is REGIME


def test_sector_bull_bear_manager_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    bull_speech, bull = agents.sector_bull(REGIME, LANES, prior='')
    bear_speech, bear = agents.sector_bear(REGIME, LANES, prior=bull_speech)
    mgr_speech, mgr = agents.research_manager(REGIME, LANES, bull_speech, bear_speech)
    assert bull['favored_lanes'] and bear['risky_lanes']
    assert mgr['winning_lanes']  # 폴백은 점수 상위 레인
    assert mgr['winning_lanes'][0] in {l['sector'] for l in LANES}


def test_stock_picker_nominates(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    # build_idea grounding은 best-effort; 실패해도 후보 자체로 지명되어야 한다.
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    speech, out = agents.stock_picker('반도체', CANDS)
    assert out['nominations'][0]['symbol'] == '000660'


def test_risk_threeway_and_manager_fallback(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    nominee = {'symbol': '000660', 'name': 'SK하이닉스',
               'timing_signal': {'signal': 'wait', 'rsi': 72, 'reason': 'RSI 72 과매수'}}
    a, _ = agents.risk_aggressive(nominee, prior='')
    b, _ = agents.risk_conservative(nominee, prior=a)
    c, _ = agents.risk_neutral(nominee, prior=b)
    speech, mgr = agents.risk_manager([nominee], debate_hist=f'{a}\n{b}\n{c}')
    assert isinstance(mgr['blocked_symbols'], list)


def test_pm_chair_ranks(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    nominees = [dict(CANDS[0]), {'symbol': '012450', 'name': '한화에어로스페이스',
                'sector': '방산', 'theme': '방산·우주', 'score': 84, 'factor_scores': {}}]
    speech, out = agents.pm_chair(REGIME, ['반도체'], nominees, risk_notes={'blocked_symbols': []})
    assert out['ranked'] and out['ranked'][0] in {n['symbol'] for n in nominees}
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_agents_roles.py -v`
Expected: FAIL — `AttributeError: module 'app.ideation.agents' has no attribute 'macro_brief'`

- [ ] **Step 3: 구현 (agents.py 끝에 append)**

```python
# ── 1단계: Macro PM ─────────────────────────────────────────────
def macro_brief(regime: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    fb = str(regime.get('summary') or '매크로 국면을 확인했습니다.')
    system = ('너는 한국 주식 운용데스크 매크로 전략가다. 주어진 국면 판정과 데이터 근거만 인용해 '
              '오늘 시장 국면을 2~3문장으로 브리핑한다. 숫자를 지어내지 마라.')
    user = _fmt({'label': regime.get('label'), 'summary': regime.get('summary'),
                 'data_basis': regime.get('data_basis')})
    speech, _ = _speak_text(system, user, fallback_text=f"{regime.get('label','')} · {fb}")
    return speech, regime


# ── 2단계: 섹터 라운드테이블 ────────────────────────────────────
def _lane_names(lanes: List[Dict[str, Any]]) -> List[str]:
    return [str(l.get('sector')) for l in lanes if l.get('sector')]


def sector_bull(regime, lanes, prior: str) -> Tuple[str, Dict[str, Any]]:
    top = sorted(lanes, key=lambda l: l.get('score', 0), reverse=True)
    fb_lanes = _lane_names(top)[:2]
    fb = f"{', '.join(fb_lanes)} 레인이 뉴스·매크로와 함께 움직여 유망합니다." if fb_lanes else '유망 레인을 점검했습니다.'
    system = ('너는 Bull 섹터 리서처다. 제공된 레인 점수·뉴스·매크로 태그만 근거로 가장 유망한 섹터 '
              '레인을 주장한다. Bear의 직전 반론이 있으면 재반박한다. '
              '응답은 {"speech": "<2~3문장>", "favored_lanes": ["<섹터>", ...]} JSON 하나.')
    user = _fmt({'regime': regime.get('label'), 'lanes': lanes, 'bear_prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'favored_lanes': fb_lanes})
    return str(parsed.get('speech') or fb), {'favored_lanes': parsed.get('favored_lanes') or fb_lanes}


def sector_bear(regime, lanes, prior: str) -> Tuple[str, Dict[str, Any]]:
    risky = sorted(lanes, key=lambda l: l.get('score', 0))[:1]
    fb_lanes = _lane_names(risky)
    fb = f"{', '.join(fb_lanes)} 레인은 과열·근거 부족 위험이 있습니다." if fb_lanes else '과열 레인을 점검했습니다.'
    system = ('너는 Bear 섹터 리서처다. 제공된 레인 점수·뉴스만 근거로 과열되었거나 근거가 약한 레인을 '
              '반박한다. Bull의 직전 주장을 구체적으로 반론한다. '
              '응답은 {"speech": "<2~3문장>", "risky_lanes": ["<섹터>", ...]} JSON 하나.')
    user = _fmt({'regime': regime.get('label'), 'lanes': lanes, 'bull_prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'risky_lanes': fb_lanes})
    return str(parsed.get('speech') or fb), {'risky_lanes': parsed.get('risky_lanes') or fb_lanes}


def research_manager(regime, lanes, bull_hist: str, bear_hist: str) -> Tuple[str, Dict[str, Any]]:
    fb_win = _lane_names(sorted(lanes, key=lambda l: l.get('score', 0), reverse=True))[:2]
    fb = f"{', '.join(fb_win)} 레인을 우선 검토 대상으로 채택합니다."
    system = ('너는 리서치 매니저다. Bull/Bear 토론을 종합해 우선 검토할 유망 섹터 레인을 1~3개 확정한다. '
              '응답은 {"speech": "<2~3문장>", "winning_lanes": ["<섹터>", ...]} JSON 하나.')
    user = _fmt({'lanes': lanes, 'bull': bull_hist, 'bear': bear_hist})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'winning_lanes': fb_win})
    win = [w for w in (parsed.get('winning_lanes') or fb_win) if w] or fb_win
    return str(parsed.get('speech') or fb), {'winning_lanes': win}


# ── 3단계: 종목 상정 ────────────────────────────────────────────
def stock_picker(lane_sector: str, candidates_in_lane: List[Dict[str, Any]]) -> Tuple[str, Dict[str, Any]]:
    noms: List[Dict[str, Any]] = []
    for c in candidates_in_lane[:3]:
        thesis = c.get('thesis') or ''
        why_now = c.get('why_now') or ''
        try:  # build_idea로 thesis/why_now grounding (best-effort)
            from ..idea_engine import build_idea
            res = build_idea(str(c.get('symbol')), horizon='3개월') or {}
            if res.get('thesis'):
                thesis = res['thesis']
            drivers = [str(d) for d in (res.get('key_drivers') or []) if str(d).strip()]
            if drivers:
                why_now = ' '.join(drivers[:3])
        except Exception:
            pass
        noms.append({'symbol': c.get('symbol'), 'name': c.get('name'), 'sector': lane_sector,
                     'theme': c.get('theme'), 'score': c.get('score'),
                     'factor_scores': c.get('factor_scores') or {},
                     'thesis': thesis, 'why_now': why_now,
                     'timing_signal': c.get('timing_signal')})
    names = ', '.join(n['name'] for n in noms) or '후보'
    return f"{lane_sector} 레인에서 {names}을(를) 상정합니다.", {'nominations': noms}


# ── 4단계: 3-way 리스크 토론 ────────────────────────────────────
def _timing_str(nominee: Dict[str, Any]) -> str:
    t = nominee.get('timing_signal') or {}
    return f"signal={t.get('signal')} rsi={t.get('rsi')} reason={t.get('reason')}"


def risk_aggressive(nominee, prior: str) -> Tuple[str, Dict[str, Any]]:
    fb = f"{nominee.get('name')} 모멘텀이 살아있어 상방 여지가 있습니다."
    system = ('너는 공격적 리스크 심의역이다. 후보의 상방·모멘텀을 강조하되 타이밍 신호를 인용한다. '
              '응답은 {"speech": "<2문장>"} JSON 하나.')
    user = _fmt({'nominee': nominee.get('name'), 'timing': _timing_str(nominee), 'prior': prior})
    speech, _ = _speak_text(system, user, fb)
    return speech, {}


def risk_conservative(nominee, prior: str) -> Tuple[str, Dict[str, Any]]:
    t = nominee.get('timing_signal') or {}
    overheated = t.get('signal') in {'wait', 'avoid'}
    fb = (f"{nominee.get('name')}은 {t.get('reason') or '과열'} — 추격매수 리스크가 있습니다."
          if overheated else f"{nominee.get('name')}의 하방·변동성을 점검해야 합니다.")
    system = ('너는 보수적 리스크 심의역이다. 과열·추격매수·하방을 타이밍 신호(RSI/MA20)를 인용해 경고한다. '
              '응답은 {"speech": "<2문장>", "block": <true/false>} JSON 하나.')
    user = _fmt({'nominee': nominee.get('name'), 'timing': _timing_str(nominee), 'prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'block': overheated})
    return str(parsed.get('speech') or fb), {'block': bool(parsed.get('block', overheated))}


def risk_neutral(nominee, prior: str) -> Tuple[str, Dict[str, Any]]:
    fb = f"{nominee.get('name')}은 분할 진입·손절선 설정 전제로 검토 가능합니다."
    system = ('너는 중립 리스크 심의역이다. 공격/보수 양측을 균형있게 판정한다. '
              '응답은 {"speech": "<2문장>"} JSON 하나.')
    user = _fmt({'nominee': nominee.get('name'), 'timing': _timing_str(nominee), 'prior': prior})
    speech, _ = _speak_text(system, user, fb)
    return speech, {}


def risk_manager(nominees: List[Dict[str, Any]], debate_hist: str) -> Tuple[str, Dict[str, Any]]:
    # 폴백: 타이밍 avoid 신호 후보를 차단
    blocked = [n.get('symbol') for n in nominees
               if (n.get('timing_signal') or {}).get('signal') == 'avoid']
    fb = (f"{len(blocked)}개 후보를 타이밍 리스크로 보류합니다." if blocked
          else '리스크 심의를 통과했습니다. 분할 진입을 권고합니다.')
    system = ('너는 리스크 매니저다. 3-way 토론을 종합해 보류할 종목(blocked_symbols)과 경고를 정한다. '
              '응답은 {"speech": "<2~3문장>", "blocked_symbols": ["<코드>", ...]} JSON 하나.')
    user = _fmt({'nominees': [n.get('symbol') for n in nominees], 'debate': debate_hist})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'blocked_symbols': blocked})
    return str(parsed.get('speech') or fb), {'blocked_symbols': parsed.get('blocked_symbols') or blocked}


# ── 5단계: PM 의장 ──────────────────────────────────────────────
def pm_chair(regime, winning_lanes, nominees, risk_notes) -> Tuple[str, Dict[str, Any]]:
    blocked = set(risk_notes.get('blocked_symbols') or [])
    ranked_all = sorted(nominees, key=lambda n: (n.get('symbol') not in blocked, n.get('score', 0)),
                        reverse=True)
    fb_ranked = [n.get('symbol') for n in ranked_all][:5]
    fb = f"{len(fb_ranked)}개 후보를 채택하고 보류 {len(blocked)}건을 반영했습니다."
    system = ('너는 PM 의장이다. 매크로·섹터·종목·리스크 회의를 종합해 채택 종목을 점수·근거로 랭킹한다. '
              '보류 종목은 후순위로 둔다. '
              '응답은 {"speech": "<3문장>", "ranked": ["<코드>", ...]} JSON 하나.')
    user = _fmt({'regime': regime.get('label'), 'winning_lanes': winning_lanes,
                 'nominees': [{'symbol': n.get('symbol'), 'name': n.get('name'),
                               'score': n.get('score')} for n in nominees],
                 'blocked': list(blocked)})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'ranked': fb_ranked})
    ranked = [r for r in (parsed.get('ranked') or fb_ranked) if r] or fb_ranked
    return str(parsed.get('speech') or fb), {'ranked': ranked}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_agents_roles.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Checkpoint**

```bash
git add backend/app/ideation/agents.py backend/tests/test_ideation_agents_roles.py
git commit -m "feat(ideation): 11-role debate agents with rule fallbacks"
```

---

## Task 5: 오케스트레이터 (`orchestrator.py`)

5단계를 순차 실행하고, 각 발언을 `stream.emit`으로 흘리며, 결과를 RadarResponse 상위호환 `decision.json`으로 조립한다.

**Files:**
- Create: `backend/app/ideation/orchestrator.py`
- Test: `backend/tests/test_ideation_orchestrator.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_orchestrator.py`:
```python
from __future__ import annotations
import json
from app.ideation.orchestrator import run_committee
from app.ideation.stream import RunStream


def test_run_committee_streams_all_stages_and_assembles(tmp_path, monkeypatch):
    # LLM 무가용 → 전 단계 룰 폴백으로 결정론 동작
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['no_llm']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    s = RunStream(tmp_path)
    decision = run_committee('AI 반도체', 3, s)

    # 1) 전 단계 stage가 messages.jsonl에 등장
    lines = [json.loads(x) for x in (tmp_path / 'messages.jsonl').read_text(encoding='utf-8').splitlines()]
    stages = {m['stage'] for m in lines}
    assert {'discovery', 'sector_debate', 'nomination', 'risk_review', 'decision'} <= stages
    assert [m['idx'] for m in lines] == list(range(len(lines)))  # idx 단조

    # 2) decision.json = RadarResponse 상위호환
    assert decision['engine'] == 'ideation_committee'
    for k in ('market_regime', 'sector_flow', 'top_picks', 'stock_candidates',
              'committee_minutes', 'transcript', 'news_flow'):
        assert k in decision
    assert len(decision['top_picks']) >= 1
    # committee_minutes는 실제 transcript(발언들)
    assert len(decision['committee_minutes']) >= 4
    # status done
    st = json.loads((tmp_path / 'status.json').read_text(encoding='utf-8'))
    assert st['stage'] == 'done'


def test_run_committee_top_picks_have_required_fields(tmp_path, monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    s = RunStream(tmp_path)
    decision = run_committee('', 3, s)
    p = decision['top_picks'][0]
    assert {'symbol', 'name', 'sector', 'score', 'thesis', 'factor_scores'} <= set(p)
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_orchestrator.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ideation.orchestrator'`

- [ ] **Step 3: 구현**

`backend/app/ideation/orchestrator.py`:
```python
from __future__ import annotations
from typing import Any, Dict, List

from . import agents
from .discovery import discover_universe
from .stream import RunStream, iso_now

MAX_SECTOR_ROUNDS = 2   # Bull,Bear 왕복 라운드 수
MAX_RISK_ROUNDS = 1     # 3-way 라운드 수

_ICON = {
    'discovery': 'activity', 'sector_debate': 'git-branch',
    'nomination': 'target', 'risk_review': 'shield', 'decision': 'gavel',
}


def run_committee(keywords: str, horizon_months: int, stream: RunStream) -> Dict[str, Any]:
    minutes: List[Dict[str, Any]] = []

    def say(agent: str, stage: str, text: str, source: str = 'rules'):
        stream.emit(agent, stage, text, icon=_ICON.get(stage, 'message'))
        minutes.append({'agent': agent, 'stage': stage, 'text': text, 'source': source,
                        'icon': _ICON.get(stage, 'message')})

    # ── 1단계: 발굴 ──
    stream.set_stage('discovery', keywords=keywords)
    universe = discover_universe(keywords, horizon_months)
    regime = universe['regime']
    macro_speech, _ = agents.macro_brief(regime)
    say('Macro PM', 'discovery', macro_speech, source=regime.get('source', 'rules'))
    say('발굴 스카우트', 'discovery',
        f"{len(universe['themes'])}개 레인·{len(universe['candidates'])}개 후보를 {universe['source']} 데이터로 발굴했습니다.",
        source=universe['source'])

    lanes = universe['sector_flow'] or [
        {'sector': t.get('sector'), 'theme': t.get('theme'), 'score': t.get('score'),
         'macro_tags': t.get('macro_tags')} for t in universe['themes']]

    # ── 2단계: 섹터 라운드테이블 ──
    stream.set_stage('sector_debate', keywords=keywords)
    bull_hist, bear_hist, prior = '', '', ''
    for _ in range(MAX_SECTOR_ROUNDS):
        bs, _b = agents.sector_bull(regime, lanes, prior=bear_hist)
        say('Bull 리서처', 'sector_debate', bs); bull_hist += ' ' + bs; prior = bs
        br, _r = agents.sector_bear(regime, lanes, prior=bull_hist)
        say('Bear 리서처', 'sector_debate', br); bear_hist += ' ' + br
    mgr_speech, mgr = agents.research_manager(regime, lanes, bull_hist, bear_hist)
    say('리서치 매니저', 'sector_debate', mgr_speech)
    winning = mgr['winning_lanes']

    # ── 3단계: 종목 상정 ──
    stream.set_stage('nomination', keywords=keywords)
    nominees: List[Dict[str, Any]] = []
    for sector in winning:
        in_lane = [c for c in universe['candidates'] if c.get('sector') == sector]
        if not in_lane:
            continue
        ps, out = agents.stock_picker(sector, in_lane)
        say('스톡피커', 'nomination', ps)
        nominees.extend(out['nominations'])
    if not nominees:  # 승리레인에 후보 없으면 전체 상위 후보 폴백
        nominees = universe['candidates'][:5]
        say('스톡피커', 'nomination', f"레인 매칭 부족 — 상위 후보 {len(nominees)}개를 상정합니다.")

    # ── 4단계: 3-way 리스크 토론 ──
    stream.set_stage('risk_review', keywords=keywords)
    debate_hist = ''
    for nominee in nominees[:5]:
        prior = ''
        for _ in range(MAX_RISK_ROUNDS):
            a, _ = agents.risk_aggressive(nominee, prior); say('공격 심의역', 'risk_review', a); prior = a
            c, _ = agents.risk_conservative(nominee, prior); say('보수 심의역', 'risk_review', c); prior = c
            n, _ = agents.risk_neutral(nominee, prior); say('중립 심의역', 'risk_review', n); prior = n
            debate_hist += f' {a} {c} {n}'
    risk_speech, risk_notes = agents.risk_manager(nominees, debate_hist)
    say('리스크 매니저', 'risk_review', risk_speech)

    # ── 5단계: PM 의장 ──
    stream.set_stage('decision', keywords=keywords)
    pm_speech, pm = agents.pm_chair(regime, winning, nominees, risk_notes)
    say('PM 의장', 'decision', pm_speech)

    decision = assemble_decision(keywords, horizon_months, universe, winning,
                                 nominees, pm['ranked'], risk_notes, minutes)
    stream.write_decision(decision)
    stream.set_stage('done', keywords=keywords)
    return decision


def assemble_decision(keywords, horizon_months, universe, winning, nominees, ranked,
                      risk_notes, minutes) -> Dict[str, Any]:
    """RadarResponse 상위호환 decision.json 조립. 기존 IdeaLab UI가 그대로 소비."""
    radar = universe.get('_radar') or {}
    by_symbol = {str(n.get('symbol')): n for n in nominees}
    blocked = set(risk_notes.get('blocked_symbols') or [])

    top_picks: List[Dict[str, Any]] = []
    for rank, sym in enumerate(ranked[:5], start=1):
        n = by_symbol.get(str(sym))
        if not n:
            continue
        top_picks.append({
            'pick_id': f"{sym}-{iso_now()[:10]}",
            'symbol': n.get('symbol'), 'name': n.get('name'), 'sector': n.get('sector'),
            'theme': n.get('theme'), 'score': n.get('score'),
            'discovery_score': n.get('score'), 'conviction_score': n.get('score'),
            'factor_scores': n.get('factor_scores') or {},
            'timing_signal': n.get('timing_signal') or {'signal': 'enter'},
            'thesis': n.get('thesis') or f"{n.get('name')} 위원회 채택 후보",
            'why_now': n.get('why_now') or '',
            'route': [universe['regime'].get('label'), n.get('sector'), n.get('theme'),
                      f"{n.get('name')}({n.get('symbol')})"],
            'counter_evidence': (['리스크 매니저 보류 대상'] if str(sym) in blocked else []),
            'checklist': ['거래대금 상위권 유지 확인', '외국인/기관 수급 연속성 확인',
                          '뉴스/공시가 실적 추정으로 연결되는지 확인'],
            'evidence': n.get('evidence') or [],
            'evidence_source': 'ideation_committee',
            'actions': ['save_history', 'single_idea', 'backtest', 'committee'],
        })
    if not top_picks and nominees:  # 랭킹 매칭 실패 폴백
        top_picks = [{**n, 'factor_scores': n.get('factor_scores') or {}} for n in nominees[:5]]

    return {
        'generated_at': iso_now(),
        'horizon_months': int(horizon_months or 3),
        'keywords': keywords,
        'engine': 'ideation_committee',
        'market_regime': universe['regime'],
        'macro_flow': radar.get('macro_flow') or universe['regime'],
        'sector_flow': universe['sector_flow'],
        'themes': universe['themes'],
        'top_picks': top_picks,
        'stock_candidates': top_picks,  # 프론트 호환 미러
        'news_flow': universe['news_flow'],
        'committee_minutes': minutes,   # ★ 실제 transcript
        'transcript': minutes,
        'pipeline': {'summary': f"{universe['regime'].get('label','')} 국면에서 위원회가 {len(top_picks)}개 후보를 채택했습니다.",
                     'stages': ['Macro', 'Sector', 'Stock']},
        'data_quality': {'mode': universe['source'],
                         'regime_source': universe['regime'].get('source'),
                         'warnings': ['실데이터 발굴 + 멀티에이전트 토론. LLM/데이터 실패 시 룰기반 폴백.']},
    }
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_orchestrator.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint**

```bash
git add backend/app/ideation/orchestrator.py backend/tests/test_ideation_orchestrator.py
git commit -m "feat(ideation): 5-stage orchestrator + RadarResponse-compatible decision"
```

---

## Task 6: Job 러너 + 워치독 (`runner.py`)

오케스트레이터를 데몬 스레드로 돌리고, committee_runner와 동일한 status/messages/result/latest API를 파일 기반으로 노출한다. 600s 워치독.

**Files:**
- Create: `backend/app/ideation/runner.py`
- Test: `backend/tests/test_ideation_runner.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_runner.py`:
```python
from __future__ import annotations
import time
from app.ideation import runner


def _wait_done(jid, timeout=20):
    for _ in range(timeout * 5):
        st = runner.get_status(jid)
        if st.get('stage') in ('done', 'error'):
            return st
        time.sleep(0.2)
    return runner.get_status(jid)


def test_start_run_completes_and_returns_result(monkeypatch, tmp_path):
    # 결정론: LLM/데이터 없이 룰 폴백
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})
    monkeypatch.setattr(runner, 'OUT_ROOT', tmp_path)

    started = runner.start_run('AI 반도체', horizon_months=3)
    jid = started['job_id']
    st = _wait_done(jid)
    assert st['stage'] == 'done'

    msgs = runner.get_messages(jid, since=0)
    assert msgs['total'] >= 5
    # since 증분
    later = runner.get_messages(jid, since=msgs['messages'][-1]['idx'])
    assert all(m['idx'] >= msgs['messages'][-1]['idx'] for m in later['messages'])

    res = runner.get_result(jid)
    assert res['engine'] == 'ideation_committee' and res['top_picks']


def test_unknown_job_is_safe():
    assert runner.get_status('nope')['stage'] == 'unknown'
    assert runner.get_messages('nope')['messages'] == []
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_runner.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.ideation.runner'`

- [ ] **Step 3: 구현**

`backend/app/ideation/runner.py`:
```python
from __future__ import annotations
import datetime as dt
import json
import threading
import traceback
from pathlib import Path
from typing import Any, Dict

from .orchestrator import run_committee
from .stream import RunStream

OUT_ROOT = Path(__file__).resolve().parents[2] / 'data' / 'idea_committee_runs'
SEED_DIR = OUT_ROOT / 'seed'
WATCHDOG_SEC = 600

_jobs: Dict[str, Dict[str, Any]] = {}


def _job_id(keywords: str) -> str:
    slug = ''.join(ch for ch in (keywords or 'all') if ch.isalnum())[:12] or 'all'
    return f"{slug}_{dt.datetime.now():%Y%m%d_%H%M%S}"


def start_run(keywords: str, horizon_months: int = 3) -> Dict[str, Any]:
    jid = _job_id(keywords)
    out_dir = OUT_ROOT / jid
    stream = RunStream(out_dir)
    stream.set_stage('starting', keywords=keywords)
    _jobs[jid] = {'keywords': keywords, 'out_dir': str(out_dir)}

    def _run():
        try:
            run_committee(keywords, horizon_months, stream)
        except Exception as e:
            stream.set_stage('error', keywords=keywords, error=str(e),
                             trace=traceback.format_exc()[-2000:])

    t = threading.Thread(target=_run, daemon=True)
    t.start()

    def _watchdog():
        t.join(WATCHDOG_SEC)
        if t.is_alive():
            stream.set_stage('error', keywords=keywords,
                             error=f'watchdog timeout {WATCHDOG_SEC}s')
    threading.Thread(target=_watchdog, daemon=True).start()
    return {'job_id': jid, 'keywords': keywords}


def get_status(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        return {'stage': 'unknown', 'job_id': job_id}
    sp = Path(job['out_dir']) / 'status.json'
    if sp.exists():
        try:
            return {**json.loads(sp.read_text(encoding='utf-8')), 'job_id': job_id}
        except Exception:
            pass
    return {'stage': 'starting', 'job_id': job_id}


def get_messages(job_id: str, since: int = 0) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        return {'messages': [], 'total': 0}
    mp = Path(job['out_dir']) / 'messages.jsonl'
    if not mp.exists():
        return {'messages': [], 'total': 0}
    out = []
    try:
        for line in mp.read_text(encoding='utf-8').splitlines():
            line = line.strip()
            if not line:
                continue
            m = json.loads(line)
            if int(m.get('idx', 0)) >= since:
                out.append(m)
    except Exception:
        pass
    return {'messages': out, 'total': len(out) + since}


def get_result(job_id: str) -> Dict[str, Any]:
    job = _jobs.get(job_id)
    if not job:
        return {'error': 'unknown job'}
    dp = Path(job['out_dir']) / 'decision.json'
    if not dp.exists():
        return {'error': 'not ready'}
    return json.loads(dp.read_text(encoding='utf-8'))


def get_latest_result() -> Dict[str, Any]:
    """최근 done job → 없으면 seed 폴백(데모 빈화면 방지)."""
    try:
        done = []
        for job in _jobs.values():
            d = Path(job['out_dir'])
            sp, dp = d / 'status.json', d / 'decision.json'
            if sp.exists() and dp.exists():
                stg = json.loads(sp.read_text(encoding='utf-8')).get('stage')
                if stg == 'done':
                    done.append(d)
        done.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for d in done:
            return json.loads((d / 'decision.json').read_text(encoding='utf-8'))
    except Exception:
        pass
    seeds = sorted(SEED_DIR.glob('*.json')) if SEED_DIR.exists() else []
    for sp in seeds:
        try:
            return json.loads(sp.read_text(encoding='utf-8'))
        except Exception:
            continue
    return {'available': False}
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_runner.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Checkpoint**

```bash
git add backend/app/ideation/runner.py backend/tests/test_ideation_runner.py
git commit -m "feat(ideation): threaded job runner with watchdog + seed fallback"
```

---

## Task 7: FastAPI 엔드포인트 (`main.py`)

**Files:**
- Modify: `backend/app/main.py` (committee 엔드포인트 근처에 추가)
- Test: `backend/tests/test_ideation_api.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_ideation_api.py`:
```python
from __future__ import annotations
import time
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_committee_run_status_messages_result(monkeypatch):
    monkeypatch.setattr('app.idea_engine._call_llm', lambda s, u: (None, None, ['x']))
    monkeypatch.setattr('app.idea_engine.build_idea', lambda *a, **k: {})

    r = client.post('/api/idea/committee/run', params={'keywords': 'AI 반도체'})
    assert r.status_code == 200
    jid = r.json()['job_id']

    for _ in range(100):
        st = client.get('/api/idea/committee/status', params={'job_id': jid}).json()
        if st['stage'] in ('done', 'error'):
            break
        time.sleep(0.2)
    assert st['stage'] == 'done'

    msgs = client.get(f'/api/idea/committee/messages/{jid}', params={'since': 0}).json()
    assert msgs['total'] >= 5

    res = client.get('/api/idea/committee/result', params={'job_id': jid}).json()
    assert res['engine'] == 'ideation_committee'
```

- [ ] **Step 2: 실패 확인**

Run: `cd backend && python -m pytest tests/test_ideation_api.py -v`
Expected: FAIL — 404 (라우트 없음)

- [ ] **Step 3: 구현 — `backend/app/main.py`에 추가**

기존 `/api/committee/*` 핸들러 블록 바로 아래에 추가:
```python
# ── 아이디에이션 위원회 (실제 멀티에이전트 발굴 토론) ──────────────
@app.post("/api/idea/committee/run")
def idea_committee_run(keywords: str = "", horizon_months: int = 3):
    from .ideation.runner import start_run
    return start_run(keywords.strip(), horizon_months)


@app.get("/api/idea/committee/status")
def idea_committee_status(job_id: str):
    from .ideation.runner import get_status
    return get_status(job_id)


@app.get("/api/idea/committee/messages/{job_id}")
def idea_committee_messages(job_id: str, since: int = 0):
    from .ideation.runner import get_messages
    return get_messages(job_id, since)


@app.get("/api/idea/committee/result")
def idea_committee_result(job_id: str):
    from .ideation.runner import get_result
    return get_result(job_id)


@app.get("/api/idea/committee/latest")
def idea_committee_latest():
    from .ideation.runner import get_latest_result
    return get_latest_result()
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && python -m pytest tests/test_ideation_api.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: 회귀 — 전체 백엔드 테스트**

Run: `cd backend && python -m pytest tests/ -q`
Expected: 기존 + 신규 모두 PASS (실패 시 import/라우트 충돌 점검)

- [ ] **Step 6: Checkpoint**

```bash
git add backend/app/main.py backend/tests/test_ideation_api.py
git commit -m "feat(ideation): committee job API endpoints"
```

---

## Task 8: LiveFeed 공용 컴포넌트 추출

AICommittee의 `LiveFeed`(+`AGENT_COLORS`/`AGENT_ICONS`)를 공용 파일로 옮겨 IdeaLab과 공유한다.

**Files:**
- Create: `frontend/src/components/committee/LiveFeed.tsx`
- Modify: `frontend/src/components/AICommittee.tsx` (인라인 LiveFeed 제거 → import)
- Test: `frontend/src/components/committee/LiveFeed.test.tsx`

- [ ] **Step 1: 공용 컴포넌트 생성**

`frontend/src/components/committee/LiveFeed.tsx` — `AICommittee.tsx:632-696`의 `LiveFeed`, `AGENT_COLORS`, `AGENT_ICONS`와 `AgentMessage` 타입을 그대로 이동하고 export. (아이콘 맵에 ideation 에이전트 추가: `'Macro PM'`, `'발굴 스카우트'`, `'리서치 매니저'`, `'스톡피커'`, `'공격 심의역'`, `'보수 심의역'`, `'중립 심의역'`, `'PM 의장'` → 적절한 lucide 아이콘; 미매핑은 기존대로 `MessagesSquare` 폴백.) `stage` 색상 맵에 `discovery/sector_debate/nomination/risk_review/decision` 추가.

```tsx
// frontend/src/components/committee/LiveFeed.tsx
import { motion, AnimatePresence } from 'framer-motion'
import {
  LineChart as LineChartIcon, HeartPulse, Newspaper, Landmark, ArrowUpRight,
  ArrowDownRight, Users, ShieldAlert, Briefcase, Gavel, MessagesSquare, Activity, Target,
} from 'lucide-react'
import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

export type AgentMessage = { idx: number; ts: string; agent: string; stage: string; text: string; icon: string }

const AGENT_COLORS: Record<string, string> = {
  analysts: 'border-l-blue/60', research_debate: 'border-l-hanwha/70',
  risk_debate: 'border-l-yellow-500/70', decision: 'border-l-up/60',
  discovery: 'border-l-blue/60', sector_debate: 'border-l-hanwha/70',
  nomination: 'border-l-blue/60', risk_review: 'border-l-yellow-500/70',
}

const AGENT_ICONS: Record<string, ReactNode> = {
  '기술적 애널리스트': <LineChartIcon size={13} />, '심리 애널리스트': <HeartPulse size={13} />,
  '뉴스 애널리스트': <Newspaper size={13} />, '재무 애널리스트': <Landmark size={13} />,
  'Bull 리서처': <ArrowUpRight size={13} />, 'Bear 리서처': <ArrowDownRight size={13} />,
  '리서치 매니저': <Users size={13} />, '리스크 매니저': <ShieldAlert size={13} />,
  '투자위원회': <Users size={13} />, '트레이더': <Briefcase size={13} />, '최종 결정': <Gavel size={13} />,
  'Macro PM': <Activity size={13} />, '발굴 스카우트': <Target size={13} />,
  '스톡피커': <Target size={13} />, '공격 심의역': <ArrowUpRight size={13} />,
  '보수 심의역': <ShieldAlert size={13} />, '중립 심의역': <Users size={13} />,
  'PM 의장': <Gavel size={13} />,
}

export function LiveFeed({ messages, feedBottomRef }: {
  messages: AgentMessage[]; feedBottomRef: React.RefObject<HTMLDivElement | null>
}) {
  return (
    <div className="mt-5">
      <div className="mb-2.5 flex items-center gap-2">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">Live Feed</span>
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-hanwha" />
        <span className="font-mono text-[10px] text-muted">{messages.length}개 발언</span>
      </div>
      <div className="max-h-72 space-y-2 overflow-y-auto rounded-[12px] border border-line/60 bg-canvas/30 p-3">
        <AnimatePresence initial={false}>
          {messages.map(m => (
            <motion.div key={m.idx} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.22 }}
              className={cn('rounded-[9px] border border-line/50 bg-card-2/40 px-3 py-2.5 border-l-4',
                AGENT_COLORS[m.stage] ?? 'border-l-line')}>
              <div className="mb-1 flex items-center gap-1.5">
                <span className="text-muted">{AGENT_ICONS[m.agent] ?? <MessagesSquare size={13} />}</span>
                <span className="font-mono text-[11px] font-bold text-greige">{m.agent}</span>
                <span className="ml-auto font-mono text-[9px] text-muted/60">
                  {m.ts ? new Date(m.ts).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''}
                </span>
              </div>
              <p className="text-[12px] leading-relaxed text-greige/90">{m.text}</p>
            </motion.div>
          ))}
        </AnimatePresence>
        <div ref={feedBottomRef} />
      </div>
    </div>
  )
}
```

- [ ] **Step 2: AICommittee.tsx에서 인라인 LiveFeed 제거 → import**

`AICommittee.tsx`: 인라인 `LiveFeed`/`AGENT_COLORS`/`AGENT_ICONS` 정의(632-696) 삭제하고 상단에 `import { LiveFeed, type AgentMessage } from './committee/LiveFeed'` 추가. 기존 로컬 `AgentMessage` 타입 선언은 import로 대체(중복 제거). 기존 사용부 `<LiveFeed messages=... feedBottomRef=... />`는 그대로.

- [ ] **Step 3: 컴포넌트 렌더 테스트**

`frontend/src/components/committee/LiveFeed.test.tsx`:
```tsx
import { render, screen } from '@testing-library/react'
import { createRef } from 'react'
import { describe, it, expect } from 'vitest'
import { LiveFeed } from './LiveFeed'

describe('LiveFeed', () => {
  it('renders agent messages with names', () => {
    const ref = createRef<HTMLDivElement>()
    render(<LiveFeed feedBottomRef={ref} messages={[
      { idx: 0, ts: '2026-06-09T10:00:00', agent: 'Macro PM', stage: 'discovery', text: 'VIX 안정', icon: 'activity' },
      { idx: 1, ts: '2026-06-09T10:00:02', agent: 'Bull 리서처', stage: 'sector_debate', text: '반도체 유망', icon: 'arrow' },
    ]} />)
    expect(screen.getByText('Macro PM')).toBeTruthy()
    expect(screen.getByText('반도체 유망')).toBeTruthy()
    expect(screen.getByText('2개 발언')).toBeTruthy()
  })
})
```

- [ ] **Step 4: 테스트/빌드 확인**

Run: `cd frontend && npx vitest run src/components/committee/LiveFeed.test.tsx`
Expected: PASS. 이어서 `npx tsc --noEmit`로 AICommittee 리팩터 타입 회귀 없는지 확인.

- [ ] **Step 5: Checkpoint**

```bash
git add frontend/src/components/committee/LiveFeed.tsx frontend/src/components/committee/LiveFeed.test.tsx frontend/src/components/AICommittee.tsx
git commit -m "refactor(committee): extract shared LiveFeed component"
```

---

## Task 9: IdeaLab 비동기 폴링 전환

"회의 시작"을 radar 동기호출에서 위원회 비동기 job 폴링으로 바꾸고, 타이머 연출을 실제 status.stage로 교체, LiveFeed를 붙인다. 결과는 RadarResponse 상위호환이라 기존 결과 컴포넌트는 그대로 둔다.

**Files:**
- Modify: `frontend/src/components/IdeaLab.tsx`
- Modify: `frontend/src/components/IdeaLab.test.tsx`

- [ ] **Step 1: STAGE_TO_PHASE 매핑 + 상태 추가**

`IdeaLab.tsx` 상단에 추가(기존 `IDEATION_PIPELINE` 4단계와 백엔드 stage 매핑):
```tsx
// 백엔드 stage → 4단계 진행카드 인덱스. discovery=0, sector_debate=1, nomination=2, risk_review/decision=3
const STAGE_TO_PHASE: Record<string, number> = {
  starting: 0, discovery: 0, sector_debate: 1, nomination: 2, risk_review: 3, decision: 3, done: 3,
}
```
`import { LiveFeed, type AgentMessage } from './committee/LiveFeed'` 추가.

- [ ] **Step 2: runRadar → runCommittee 폴링으로 교체**

`runRadar` 콜백과 `useEffect`(setInterval 타이머, 209-215)를 다음으로 교체. messages 2초, status 5초 폴링, since 증분, done 시 result fetch. 언마운트 타이머 정리.
```tsx
const [messages, setMessages] = useState<AgentMessage[]>([])
const pollRef = useRef<number | null>(null)
const msgRef = useRef<number | null>(null)
const sinceRef = useRef(0)
const feedBottomRef = useRef<HTMLDivElement | null>(null)

const stopTimers = useCallback(() => {
  if (pollRef.current) window.clearInterval(pollRef.current)
  if (msgRef.current) window.clearInterval(msgRef.current)
  pollRef.current = null; msgRef.current = null
}, [])

useEffect(() => () => stopTimers(), [stopTimers])

const runRadar = useCallback(async () => {
  setRadarState('loading'); setRadarError(''); setActivePhase(0)
  setSelectedCandidate(null); setRadar(null); setMessages([]); sinceRef.current = 0
  stopTimers()
  try {
    const params = new URLSearchParams({ horizon_months: '3' })
    if (keywords.trim()) params.set('keywords', keywords.trim())
    const r = await fetch(`${apiBase}/api/idea/committee/run?${params.toString()}`, { method: 'POST' })
    if (!r.ok) throw new Error(`run failed: ${r.status}`)
    const { job_id } = await r.json()
    if (!job_id) throw new Error('job_id 없음')

    msgRef.current = window.setInterval(async () => {
      try {
        const md = await fetch(`${apiBase}/api/idea/committee/messages/${job_id}?since=${sinceRef.current}`).then(x => x.json())
        if (md.messages?.length) {
          setMessages(prev => [...prev, ...md.messages])
          sinceRef.current = md.messages[md.messages.length - 1].idx + 1
          setTimeout(() => feedBottomRef.current?.scrollIntoView({ behavior: 'smooth' }), 50)
        }
      } catch { /* best-effort */ }
    }, 2000)

    pollRef.current = window.setInterval(async () => {
      try {
        const s = await fetch(`${apiBase}/api/idea/committee/status?job_id=${job_id}`).then(x => x.json())
        if (typeof s.stage === 'string' && s.stage in STAGE_TO_PHASE) setActivePhase(STAGE_TO_PHASE[s.stage])
        if (s.stage === 'done') {
          stopTimers()
          const d: RadarResponse = await fetch(`${apiBase}/api/idea/committee/result?job_id=${job_id}`).then(x => x.json())
          setRadar(d)
          const next = d.stock_candidates?.length ? d.stock_candidates : d.top_picks ?? []
          setSelectedCandidate(next[0] ?? null)
          setRadarState('done'); setActivePhase(IDEATION_PIPELINE.length - 1)
        } else if (s.stage === 'error' || s.stage === 'unknown') {
          stopTimers(); setRadarError(s.error ?? '위원회 실행 실패'); setRadarState('error')
        }
      } catch (e) {
        stopTimers(); setRadarError(e instanceof Error ? e.message : '상태 조회 실패'); setRadarState('error')
      }
    }, 5000)
  } catch (e) {
    stopTimers(); setRadar(null); setSelectedCandidate(null)
    setRadarError(e instanceof Error ? e.message : '위원회 실행 실패'); setRadarState('error')
  }
}, [apiBase, keywords, stopTimers])
```
**삭제:** 기존 5초 `setInterval`로 activePhase를 올리던 `useEffect`(209-215). 이제 status가 단계를 구동한다.

- [ ] **Step 3: 진행 중 LiveFeed 렌더**

`IdeationWorkflow` 카드 아래(또는 그 컴포넌트 내부)에 로딩 중이고 발언이 있으면 LiveFeed 표시:
```tsx
{radarState === 'loading' && messages.length > 0 && (
  <LiveFeed messages={messages} feedBottomRef={feedBottomRef} />
)}
```

- [ ] **Step 4: 테스트 갱신**

`IdeaLab.test.tsx`: 기존 radar 단일 fetch mock을 job 플로우 mock으로 교체 — `POST .../run`→`{job_id:'j1'}`, `status`→`{stage:'done'}`, `messages/j1`→`{messages:[...], total:n}`, `result`→ RadarResponse 형 decision. "회의 시작" 클릭 후 후보가 렌더되는지 검증. (fetch는 URL 분기 mock.)
```tsx
// 핵심: global.fetch를 URL 패턴으로 분기
vi.stubGlobal('fetch', vi.fn((url: string, opts?: any) => {
  if (url.includes('/committee/run')) return Promise.resolve({ ok: true, json: () => Promise.resolve({ job_id: 'j1' }) })
  if (url.includes('/committee/status')) return Promise.resolve({ json: () => Promise.resolve({ stage: 'done' }) })
  if (url.includes('/committee/messages')) return Promise.resolve({ json: () => Promise.resolve({ messages: [], total: 0 }) })
  if (url.includes('/committee/result')) return Promise.resolve({ json: () => Promise.resolve({
    generated_at: '2026-06-09T10:00:00', engine: 'ideation_committee', top_picks: [
      { symbol: '000660', name: 'SK하이닉스', sector: '반도체', theme: 'AI 인프라', score: 86, factor_scores: {}, thesis: 't', why_now: 'w' }],
    stock_candidates: [], sector_flow: [], committee_minutes: [], news_flow: [] }) })
  return Promise.resolve({ ok: true, json: () => Promise.resolve({}) })
}))
```
타이머가 동작하도록 `vi.useFakeTimers()` + `act`로 인터벌 진행, 또는 폴링 간격을 테스트 시 짧게(상수화) — 구현 시 `STATUS_MS`/`MSG_MS` 상수를 export해 테스트에서 단축 권장.

- [ ] **Step 5: 테스트/타입 확인**

Run: `cd frontend && npx vitest run src/components/IdeaLab.test.tsx && npx tsc --noEmit`
Expected: PASS, 타입 에러 없음.

- [ ] **Step 6: Checkpoint**

```bash
git add frontend/src/components/IdeaLab.tsx frontend/src/components/IdeaLab.test.tsx
git commit -m "feat(idealab): real async committee polling + live feed, remove timer"
```

---

## Task 10: Seed 런 캐시 + 데모 리허설 + 전체 회귀

데모 중 빈 화면 방지를 위해 known-good `decision.json`을 seed로 저장하고, 전 구간을 한 번 돌려 확인한다.

**Files:**
- Create: `backend/data/idea_committee_runs/seed/ideation_seed.json` (스크립트 생성)
- Create: `backend/scripts/make_ideation_seed.py`

- [ ] **Step 1: seed 생성 스크립트**

`backend/scripts/make_ideation_seed.py`:
```python
"""오프라인 1회 실행으로 known-good decision.json을 seed로 저장.

실데이터/LLM이 있으면 그 결과를, 없으면 룰 폴백 결과를 저장한다(어느 쪽이든 유효).
실행: cd backend && python scripts/make_ideation_seed.py
"""
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ideation.stream import RunStream
from app.ideation.orchestrator import run_committee
from app.ideation.runner import SEED_DIR

def main():
    tmp = SEED_DIR.parent / '_seed_build'
    s = RunStream(tmp)
    decision = run_committee('AI 반도체 전력망 방산', 3, s)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    (SEED_DIR / 'ideation_seed.json').write_text(
        __import__('json').dumps(decision, ensure_ascii=False, indent=2), encoding='utf-8')
    print('seed written:', SEED_DIR / 'ideation_seed.json', '| picks:', len(decision['top_picks']))

if __name__ == '__main__':
    main()
```

- [ ] **Step 2: seed 생성 실행**

Run: `cd backend && python scripts/make_ideation_seed.py`
Expected: `seed written: .../seed/ideation_seed.json | picks: N` (N≥1). 파일 생성 확인.

- [ ] **Step 3: latest 폴백 검증**

`backend/tests/test_ideation_runner.py`에 추가:
```python
def test_latest_falls_back_to_seed_when_no_live(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, 'OUT_ROOT', tmp_path)
    monkeypatch.setattr(runner, 'SEED_DIR', tmp_path / 'seed')
    (tmp_path / 'seed').mkdir(parents=True)
    (tmp_path / 'seed' / 's.json').write_text('{"engine":"ideation_committee","top_picks":[1]}', encoding='utf-8')
    runner._jobs.clear()
    res = runner.get_latest_result()
    assert res['engine'] == 'ideation_committee'
```
Run: `cd backend && python -m pytest tests/test_ideation_runner.py -v` → PASS.

- [ ] **Step 4: 전체 회귀**

Run: `cd backend && python -m pytest tests/ -q`
Then: `cd frontend && npx vitest run && npx tsc --noEmit`
Expected: 전부 PASS, 타입 클린.

- [ ] **Step 5: 수동 데모 리허설 (런북)**

1. 백엔드 기동: `cd backend && uvicorn app.main:app --reload`
2. 프론트 기동: `cd frontend && npm run dev`
3. IdeaLab 탭 → 키워드 "AI 반도체" → "회의 시작".
4. 확인: 4단계 카드가 **실제 stage**로 진행, LiveFeed에 에이전트 발언 누적, 완료 시 회의록(committee_minutes)이 **실제 transcript**, 후보 클릭 시 결정 리포트 표시.
5. LLM 키 없이도(룰 폴백) 끝까지 완주하는지 확인.

- [ ] **Step 6: Checkpoint**

```bash
git add backend/scripts/make_ideation_seed.py backend/data/idea_committee_runs/seed/ideation_seed.json backend/tests/test_ideation_runner.py
git commit -m "feat(ideation): seed cache for demo + latest fallback test"
```

---

## 완료 기준 (Definition of Done)

- [ ] `backend/app/ideation/` 5개 모듈 + 5개 테스트 파일 전부 PASS.
- [ ] `/api/idea/committee/{run,status,messages,result,latest}` 동작, 기존 백엔드 테스트 회귀 없음.
- [ ] IdeaLab "회의 시작" → 실제 비동기 토론 + LiveFeed 스트리밍 + 실제 transcript 회의록.
- [ ] LLM/데이터 없이도(룰 폴백) hard-fail 없이 완주, seed 폴백으로 데모 빈화면 없음.
- [ ] 프론트 vitest + tsc 클린.

## Self-Review 메모 (작성자 점검 완료)

- **스펙 커버리지**: 5단계·11역할·3-way 리스크·동적발굴(radar 흡수)·스트리밍 계약·RadarResponse 상위호환·데모 seed 폴백 — 전부 Task로 매핑됨(Task1=stream, 2=discovery, 3-4=agents, 5=orchestrator, 6=runner, 7=API, 8-9=front, 10=seed/회귀).
- **타입 일관성**: `discover_universe`→`universe` 키(regime/themes/candidates/sector_flow/news_flow/source/_radar)가 orchestrator·assemble_decision에서 동일하게 사용됨. agents 반환 (speech, dict) 형태 일관. `RunStream.emit/set_stage/write_decision` 시그니처 전 Task 동일.
- **플레이스홀더 없음**: 모든 코드 스텝에 실제 코드 포함. 폴백 경로 명시.
- **알려진 트레이드오프**: build_idea 직렬 호출(3단계)은 후보 수만큼 LLM 지연 → 필요 시 ThreadPoolExecutor 병렬화는 후속 최적화로 남김(YAGNI, 정확성 우선).
