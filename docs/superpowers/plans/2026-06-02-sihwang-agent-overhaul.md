# 시황에이전트 전면 개편 — 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(권장) 또는 superpowers:executing-plans 로 task 단위 실행. 체크박스(`- [ ]`)로 추적.
>
> **이 저장소는 git이 아님** → 각 task 끝 "체크포인트"는 커밋 대신 수동 검증/진행 표시. 백엔드 수정 후에는 uvicorn 수동 재시작(아래 공통 절차).

**Goal:** 시황 브리핑을 슬롯별 페르소나(장전=한지영 / 장마감=강진혁 / 장중=아침시황)·고유 구조·통일 템플릿(앱 UI + PNG)으로 전면 개편한다.

**Architecture:** `generate_report_sections(slot, market_data)`가 슬롯 공통 **envelope**(persona·title·stance·headline·blocks·legacy)를 반환. 슬롯 차이는 blocks로만 표현. 프론트 `BriefingReport`가 envelope를 블록 렌더. PNG는 장전/장마감=hanwha 1p 재디자인, 장중=tele 3p 개선. `legacy` 9키 매핑으로 기존 PNG 파이프라인 무손상 점진 이행.

**Tech Stack:** Python 3.9(FastAPI/anthropic/playwright/pykrx), React 19+Vite+Tailwind+framer-motion, Vitest, pytest.

**스펙:** `docs/superpowers/specs/2026-06-02-sihwang-agent-overhaul-design.md`

---

## 공통 절차

- 백엔드 테스트: `cd ai-investment-desk-os/backend; $env:PYTHONPATH=(Get-Location).Path; python -X utf8 -m pytest tests/<f> -q`
- 백엔드 재시작(코드 반영): 8000 포트 python 종료 후 `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`(reload 미사용 — Windows 좀비 이슈).
- 프론트: `cd ai-investment-desk-os/frontend; npx tsc --noEmit; npm test -- --run`. dev 서버는 HMR로 자동 반영.
- envelope를 만지는 백엔드 작업은 `committee_engine/TradingAgents/.env`의 ANTHROPIC_API_KEY가 주입되어 LLM 경로가 동작(`app.main` import 시 주입). 단위 테스트는 LLM을 monkeypatch 해 결정론으로 검증.

---

## 파일 구조 (생성/수정 맵)

| 파일 | 역할 | 작업 |
| --- | --- | --- |
| `backend/sitele/report_schema.py` | envelope 스키마·SLOT_BLOCKS·검증·legacy 매핑 (신규, 단일 책임) | Create |
| `backend/sitele/hanwha_report_text.py` | 3 페르소나 프롬프트 + envelope 생성/파싱/폴백 | Modify |
| `backend/sitele/run_intraday.py` | 장중 데이터 보강(KOSDAQ 섹터·무버·RS) | Modify |
| `backend/sitele/hanwha_report_renderer.py` | 장전/장마감 1p PNG (envelope 렌더) | Modify |
| `backend/sitele/hanwha_report_template.html` | 장전/장마감 PNG 템플릿 재디자인 | Modify |
| `backend/sitele/report_renderer_tele.py` | 장중 3p PNG (envelope→analysis_text) | Modify |
| `backend/app/briefing.py` | `report`(envelope)·`png_paths` 캡처/반환 | Modify |
| `backend/tests/test_report_schema.py` | 스키마·검증·legacy 테스트 | Create |
| `backend/tests/test_briefing_envelope.py` | generate_report_sections envelope/폴백 | Create |
| `frontend/src/components/briefing/types.ts` | envelope 타입 | Modify |
| `frontend/src/components/briefing/BriefingReport.tsx` | 블록 렌더러 (신규) | Create |
| `frontend/src/components/briefing/PngCard.tsx` | 다중 PNG 갤러리 | Modify |
| `frontend/src/components/briefing/index.ts` | export 추가 | Modify |
| `frontend/src/components/BriefingAgent.tsx` | report 소비·persona 헤더·장중 토글 | Modify |
| `frontend/src/components/briefing/BriefingReport.test.tsx` | 블록 렌더 테스트 | Create |

---

## Phase A — 백엔드 콘텐츠 엔진

### Task A1: envelope 스키마 + SLOT_BLOCKS + 검증/legacy 매핑

**Files:**
- Create: `backend/sitele/report_schema.py`
- Test: `backend/tests/test_report_schema.py`

- [ ] **Step 1: 실패 테스트 작성**

`backend/tests/test_report_schema.py`:
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sitele"))

import report_schema as rs


def test_slot_blocks_define_five_blocks_each():
    for slot in ("premarket", "intraday", "close"):
        spec = rs.SLOT_BLOCKS[slot]
        assert len(spec) == 5
        assert all({"id", "label", "type"} <= set(b) for b in spec)


def test_normalize_envelope_fills_missing_blocks_and_stance():
    raw = {"title": "테스트 제목·시장·판단", "stance": "BOGUS",
           "headline": "요약", "blocks": [
               {"id": "global_kr", "type": "paragraph", "body": "문단"}]}
    env = rs.normalize_envelope("premarket", raw)
    assert env["slot"] == "premarket"
    assert env["persona"] == "한지영"
    assert env["stance"] == "NEUTRAL"          # 잘못된 stance 보정
    assert len(env["blocks"]) == 5             # 누락 블록 채움
    ids = [b["id"] for b in env["blocks"]]
    assert ids == [b["id"] for b in rs.SLOT_BLOCKS["premarket"]]  # 순서 고정
    assert env["blocks"][0]["body"] == "문단"   # 제공분 보존


def test_legacy_mapping_has_nine_keys():
    env = rs.normalize_envelope("close", {"title": "마감·수급·판단",
                                          "stance": "RISK-OFF", "headline": "h",
                                          "blocks": []})
    legacy = rs.to_legacy(env)
    assert {"title", "stance", "key_issue", "bull_case", "bear_case",
            "macro_flow", "kr_outlook", "strategy", "news_flow"} <= set(legacy)
    assert legacy["title"] == "마감·수급·판단"
    assert legacy["stance"] == "RISK-OFF"


def test_fallback_envelope_is_complete():
    env = rs.fallback_envelope("intraday", reason="no_llm")
    assert env["slot"] == "intraday"
    assert len(env["blocks"]) == 5
    assert all(b.get("body") not in (None, "", []) for b in env["blocks"])
```

- [ ] **Step 2: 실패 확인** — `pytest tests/test_report_schema.py -q` → ImportError(report_schema 없음).

- [ ] **Step 3: 구현**

`backend/sitele/report_schema.py`:
```python
# -*- coding: utf-8 -*-
"""시황 envelope 스키마 · 슬롯별 블록 정의 · 검증 · 레거시(9키) 매핑."""
from __future__ import annotations
from typing import Any

PERSONA = {"premarket": "한지영", "intraday": "아침시황", "close": "강진혁"}
VALID_STANCES = {"RISK-ON", "NEUTRAL", "RISK-OFF"}

# 슬롯별 블록 순서·라벨·타입(bullets|paragraph|kv). 프론트/PNG/검증 공통 단일 소스.
SLOT_BLOCKS: dict[str, list[dict[str, str]]] = {
    "premarket": [
        {"id": "global_kr",       "label": "글로벌 마감 → 국내 영향", "type": "paragraph"},
        {"id": "key3",            "label": "오늘의 핵심 포인트 3",     "type": "bullets"},
        {"id": "macro",           "label": "매크로 · 금리 · 환율",     "type": "kv"},
        {"id": "sector_strategy", "label": "주목 섹터 · 전략",         "type": "bullets"},
        {"id": "checkpoint",      "label": "운용 체크포인트",          "type": "bullets"},
    ],
    "intraday": [
        {"id": "kospi_theme",  "label": "KOSPI 흐름 · 주도 테마",  "type": "paragraph"},
        {"id": "kosdaq_theme", "label": "KOSDAQ 흐름 · 주도 테마", "type": "paragraph"},
        {"id": "sector_rs",    "label": "섹터 · RS 동향",          "type": "bullets"},
        {"id": "breadth_flow", "label": "등락 · 수급",             "type": "kv"},
        {"id": "headlines",    "label": "주요 헤드라인",            "type": "bullets"},
    ],
    "close": [
        {"id": "wrap",     "label": "마감 총평",        "type": "paragraph"},
        {"id": "flows",    "label": "주체별 수급",      "type": "kv"},
        {"id": "sectors",  "label": "주도 · 부진 섹터", "type": "bullets"},
        {"id": "movers",   "label": "특징주",          "type": "bullets"},
        {"id": "tomorrow", "label": "내일 관전 포인트", "type": "bullets"},
    ],
}

# legacy 9키 ← envelope 블록 매핑(블록 id 우선순위로 채움)
_LEGACY_FROM = {
    "key_issue":  ["key3", "wrap", "kospi_theme"],
    "bull_case":  ["sector_strategy", "sectors", "sector_rs"],
    "bear_case":  ["checkpoint", "tomorrow", "breadth_flow"],
    "macro_flow": ["macro", "flows", "breadth_flow"],
    "kr_outlook": ["global_kr", "wrap", "kosdaq_theme"],
    "strategy":   ["sector_strategy", "tomorrow", "sector_rs"],
    "news_flow":  ["headlines", "movers", "sectors"],
}


def _empty_body(btype: str) -> Any:
    return {"bullets": ["—"], "paragraph": "—", "kv": [{"k": "—", "v": "—"}]}[btype]


def _coerce_body(btype: str, body: Any) -> Any:
    if body in (None, "", [], {}):
        return _empty_body(btype)
    if btype == "bullets":
        if isinstance(body, str):
            return [ln.strip(" -•·") for ln in body.splitlines() if ln.strip()] or ["—"]
        return [str(x).strip(" -•·") for x in body if str(x).strip()] or ["—"]
    if btype == "paragraph":
        if isinstance(body, list):
            return " ".join(str(x) for x in body) or "—"
        return str(body)
    # kv
    out = []
    if isinstance(body, dict):
        body = [{"k": k, "v": v} for k, v in body.items()]
    for item in body if isinstance(body, list) else []:
        if isinstance(item, dict) and ("k" in item or "v" in item):
            out.append({"k": str(item.get("k", "")), "v": str(item.get("v", "")),
                        "tone": item.get("tone", "neutral")})
    return out or _empty_body("kv")


def normalize_envelope(slot: str, raw: dict[str, Any]) -> dict[str, Any]:
    """LLM 산출 raw dict를 슬롯 규격 envelope로 정규화(누락 보정·순서 고정)."""
    spec = SLOT_BLOCKS.get(slot)
    if spec is None:
        raise ValueError(f"unknown slot: {slot!r}")
    raw = raw or {}
    given = {str(b.get("id")): b for b in (raw.get("blocks") or []) if isinstance(b, dict)}

    blocks = []
    for s in spec:
        src = given.get(s["id"], {})
        blocks.append({
            "id": s["id"], "label": s["label"], "type": s["type"],
            "body": _coerce_body(s["type"], src.get("body")),
        })

    stance = str(raw.get("stance", "")).upper().strip()
    if stance not in VALID_STANCES:
        stance = "NEUTRAL"
    title = str(raw.get("title", "")).strip() or f"{PERSONA[slot]} 시황 브리핑"
    headline = str(raw.get("headline", "")).strip() or "—"

    return {
        "slot": slot, "persona": PERSONA[slot], "title": title,
        "stance": stance, "headline": headline, "blocks": blocks,
    }


def _block_text(block: dict[str, Any]) -> str:
    body = block.get("body")
    if isinstance(body, list):
        if body and isinstance(body[0], dict):  # kv
            return "\n".join(f"- {i.get('k')}: {i.get('v')}" for i in body)
        return "\n".join(f"- {x}" for x in body)
    return str(body or "—")


def to_legacy(env: dict[str, Any]) -> dict[str, Any]:
    """기존 PNG/렌더러 호환용 9키 매핑."""
    by_id = {b["id"]: b for b in env.get("blocks", [])}
    legacy = {"title": env.get("title", "—"), "stance": env.get("stance", "NEUTRAL")}
    for key, candidates in _LEGACY_FROM.items():
        text = "—"
        for cid in candidates:
            if cid in by_id:
                text = _block_text(by_id[cid]); break
        legacy[key] = text
    return legacy


def fallback_envelope(slot: str, reason: str = "") -> dict[str, Any]:
    """LLM 미가용 시 슬롯별 완결 폴백(공백 금지)."""
    spec = SLOT_BLOCKS[slot]
    raw_blocks = [{"id": s["id"], "body": _empty_body(s["type"])} for s in spec]
    env = normalize_envelope(slot, {
        "title": f"{PERSONA[slot]} 시황 — 데이터 준비 중",
        "stance": "NEUTRAL",
        "headline": f"분석 텍스트 생성 보류 중{f' ({reason})' if reason else ''}. 데이터 패널을 참고하세요.",
        "blocks": raw_blocks,
    })
    return env
```

- [ ] **Step 4: 통과 확인** — `pytest tests/test_report_schema.py -q` → 4 passed.
- [ ] **Step 5: 체크포인트** — report_schema 단위 통과 기록.

### Task A2: 3 페르소나 시스템 프롬프트

**Files:** Modify `backend/sitele/hanwha_report_text.py`

- [ ] **Step 1: 프롬프트 상수 추가** — 기존 `SYSTEM_PROMPT`(31~105행)는 보존하되, 아래 3개를 그 아래에 추가. 각 프롬프트는 **envelope JSON**(`title/stance/headline/blocks[{id,body}]`)만 출력하도록 지시하고, 블록 id는 해당 슬롯 `SLOT_BLOCKS` id와 일치해야 함을 명시.

```python
from report_schema import SLOT_BLOCKS  # 파일 상단 import 영역에 추가

def _blocks_contract(slot: str) -> str:
    lines = [f'    {{"id":"{b["id"]}", "body":<{b["type"]}>}}  // {b["label"]}'
             for b in SLOT_BLOCKS[slot]]
    return "\n".join(lines)

_COMMON_RULES = """
공통 규칙:
- 모든 판단은 수치(지수·등락률%·금리%·환율원·수급 억원·PER/PBR 등)에 근거. 상투어("전반적으로","지켜볼 필요") 금지.
- 이모지·특정 종목 매수/매도 추천 금지(섹터 수준까지). "반드시/확실히" 단정 금지.
- 출력은 순수 JSON 하나(마크다운 코드블록 금지). 스키마:
  {"title": "주도변수·시장반응·판단", "stance": "RISK-ON|NEUTRAL|RISK-OFF",
   "headline": "핵심 2~3문장", "blocks": [ <아래 블록들, id 고정·순서 유지> ]}
- body 타입: paragraph=문자열, bullets=문자열 배열(3~5개), kv=[{"k":지표,"v":값/해석,"tone":"up|down|neutral"}].
"""

PROMPT_PREMARKET_HANJIYOUNG = f"""당신은 한지영 스타일의 매크로 전략 애널리스트입니다(증권사 리서치 모닝 전략 노트 톤).
글로벌 → 국내로 내려오는 톱다운 인과체인을 차분하고 논리적인 '~할 전망/~로 판단' 정중·분석 서술체로 씁니다.
간밤 미국 증시·금리·환율·원자재가 오늘 국내 장 시초에 어떤 경로로 영향을 주는지, 컨센서스 대비 무엇이 괴리인지에 집중합니다.
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('premarket')}
"""

PROMPT_CLOSE_KANGJINHYUK = f"""당신은 강진혁 스타일의 마감 시황 애널리스트입니다(장 마감 코멘트 톤).
팩트 먼저·해석 다음·액션 마지막으로 짧고 단단하게 씁니다. 주체별 수급(외국인/기관/개인 현·선물)과 섹터·특징주로 오늘 장을 결산하고 내일 관전 포인트를 제시합니다.
간결 임팩트체. 한 문장 한 메시지.
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('close')}
"""

PROMPT_INTRADAY_MORNING = f"""당신은 한화손보 운용본부의 '아침시황' 작성자입니다.
KOSPI·KOSDAQ 각각의 흐름과 그날의 주도 섹터/테마를 ■ 헤더형 내러티브처럼 설명하고, RS·섹터 등락·등락종목수·수급·헤드라인을 데이터로 연결합니다.
섹터 주도주 스토리(왜 그 테마가 움직이는가) 중심의 실무 브리핑 톤.
{_COMMON_RULES}
blocks(이 순서·id 고정):
{_blocks_contract('intraday')}
"""

_SLOT_SYSTEM = {
    "premarket": PROMPT_PREMARKET_HANJIYOUNG,
    "close":     PROMPT_CLOSE_KANGJINHYUK,
    "intraday":  PROMPT_INTRADAY_MORNING,
}
```

- [ ] **Step 2: 검증** — `python -X utf8 -c "import sys; sys.path.insert(0,'sitele'); import hanwha_report_text as h; print(list(h._SLOT_SYSTEM), 'global_kr' in h.PROMPT_PREMARKET_HANJIYOUNG)"` → `['premarket','close','intraday'] True`.
- [ ] **Step 3: 체크포인트.**

### Task A3: generate_report_sections → envelope 출력

**Files:** Modify `backend/sitele/hanwha_report_text.py` (629~686행 `generate_report_sections`, 489~561 파서/폴백)

- [ ] **Step 1: 파서/후처리 교체** — `_parse_sections`/`_postprocess_sections`/`_fallback_sections`를 envelope 기반으로 대체. 핵심: LLM raw → `_extract_json` → `report_schema.normalize_envelope(slot, raw)`; 지수 레벨 sanitize(`_sanitize_breakout_levels`)는 `blocks` 중 type==paragraph/bullets 본문 텍스트에만 적용. 폴백은 `report_schema.fallback_envelope(slot, reason)`.

```python
import report_schema as _schema

def _extract_json(raw: str) -> dict | None:
    import json, re
    m = re.search(r"\{[\s\S]*\}", raw or "")
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None

def _postprocess_envelope(env: dict, market_data: dict) -> dict:
    kospi_level = _get_kospi_level(market_data)
    for b in env.get("blocks", []):
        if b["type"] == "paragraph" and isinstance(b["body"], str):
            b["body"] = _sanitize_breakout_levels(
                b["body"].replace("한화생명보험", "한화손해보험").replace("한화생명", "한화손해보험"),
                kospi_level)
        elif b["type"] == "bullets":
            b["body"] = [_sanitize_breakout_levels(str(x), kospi_level) for x in b["body"]]
    return env
```

- [ ] **Step 2: generate_report_sections 본문 교체** — system 프롬프트를 `_SLOT_SYSTEM[slot]`로, 결과를 `normalize_envelope`→`_postprocess_envelope`로. anthropic/codex/fallback 3경로 유지. 반환 envelope에 `as_of`(ISO)와 `legacy=to_legacy(env)` 추가.

```python
def generate_report_sections(slot: str, market_data: dict) -> dict[str, Any]:
    import datetime as _dt
    builders = {"premarket": _build_premarket_prompt,
                "intraday": _build_intraday_prompt, "close": _build_close_prompt}
    builder = builders.get(slot)
    if builder is None:
        raise ValueError(f"알 수 없는 슬롯: {slot!r}")
    user_prompt = builder(market_data)
    system = _SLOT_SYSTEM[slot]

    def _finish(raw_text: str | None, reason: str = "") -> dict:
        parsed = _extract_json(raw_text or "")
        if parsed is None:
            env = _schema.fallback_envelope(slot, reason or "json_parse_failed")
        else:
            env = _postprocess_envelope(_schema.normalize_envelope(slot, parsed), market_data)
        env["as_of"] = _dt.datetime.now().isoformat(timespec="seconds")
        env["legacy"] = _schema.to_legacy(env)
        return env

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if _ANTHROPIC_OK and api_key:
        try:
            client = anthropic.Anthropic(api_key=api_key)
            msg = client.messages.create(model="claude-sonnet-4-6", max_tokens=2600,
                system=system, messages=[{"role": "user", "content": user_prompt}])
            return _finish(msg.content[0].text)
        except Exception as exc:
            print(f"[WARN] Claude API 실패: {exc} → Codex")
    try:
        # _call_via_codex 는 SYSTEM_PROMPT 상수를 쓰므로 system 인자화 필요(Step 3)
        raw = _call_via_codex(user_prompt, system=system)
        if raw:
            return _finish(raw)
    except Exception as exc:
        print(f"[WARN] Codex 실패: {exc}")
    return _finish(None, "ANTHROPIC_API_KEY 없음 + Codex 실패" if not api_key else "API 실패")
```

- [ ] **Step 3: `_call_via_codex` 시그니처에 `system` 추가** — 565행 `def _call_via_codex(user_prompt: str)` → `def _call_via_codex(user_prompt: str, system: str = SYSTEM_PROMPT)`, 본문 `full_prompt`의 `SYSTEM_PROMPT` → `system`.
- [ ] **Step 4: 체크포인트.**

### Task A4: generate_report_sections envelope 테스트(LLM monkeypatch)

**Files:** Create `backend/tests/test_briefing_envelope.py`

- [ ] **Step 1: 테스트 작성**
```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "sitele"))
import hanwha_report_text as h


def _fake_llm_json(slot):
    import report_schema as rs
    blocks = [{"id": b["id"], "body": ("문단" if b["type"] == "paragraph"
              else ["a", "b", "c"] if b["type"] == "bullets"
              else [{"k": "VIX", "v": "16.1", "tone": "neutral"}])}
              for b in rs.SLOT_BLOCKS[slot]]
    return '{"title":"주도·반응·판단","stance":"RISK-ON","headline":"요약","blocks":' + str(blocks).replace("'", '"') + '}'


def test_envelope_per_slot(monkeypatch):
    for slot in ("premarket", "intraday", "close"):
        monkeypatch.setattr(h.os, "environ", {"ANTHROPIC_API_KEY": ""})  # SDK 경로 skip
        monkeypatch.setattr(h, "_call_via_codex", lambda *a, **k: _fake_llm_json(slot))
        env = h.generate_report_sections(slot, {"kr_indices": {"kospi": {"close": 2700}}})
        assert env["slot"] == slot and len(env["blocks"]) == 5
        assert env["stance"] == "RISK-ON"
        assert {"title", "key_issue", "news_flow"} <= set(env["legacy"])
        assert env["as_of"]


def test_envelope_fallback_when_no_llm(monkeypatch):
    monkeypatch.setattr(h.os, "environ", {"ANTHROPIC_API_KEY": ""})
    monkeypatch.setattr(h, "_call_via_codex", lambda *a, **k: "")
    env = h.generate_report_sections("close", {})
    assert len(env["blocks"]) == 5 and env["legacy"]["title"]
```

- [ ] **Step 2: 실행** — `pytest tests/test_briefing_envelope.py -q` → 2 passed.
- [ ] **Step 3: 체크포인트.**

---

## Phase B — 데이터 보강 · briefing.py 배선

### Task B1: 장중 데이터에 KOSDAQ 섹터·무버·RS 보강

**Files:** Modify `backend/sitele/run_intraday.py` (`_collect_intraday_data`, 165~178행 반환 dict)

- [ ] **Step 1:** `raw = adf.get_complete_report_data()` 결과에서 아래를 반환 dict에 추가(이미 `briefing.py _build_interactive_data`가 같은 키를 쓰므로 동일 소스):
```python
        "kosdaq_sectors": raw.get("kosdaqSectors", []) or [],
        "rs_kospi":       raw.get("rsData", []) or [],
        "rs_kosdaq":      raw.get("kosdaqRsData", []) or [],
        "top_gainers":    raw.get("topGainers", []) or [],
        "top_losers":     raw.get("topLosers", []) or [],
```
- [ ] **Step 2: 검증** — `python -X utf8 run_intraday.py` 없이, `python -X utf8 -c "import sys;sys.path.insert(0,'sitele');import run_intraday as r;d=r._collect_intraday_data();print('kosdaq_sectors' in d,'rs_kospi' in d)"` → `True True`(네트워크 실패해도 키 존재).
- [ ] **Step 3: 체크포인트.**

### Task B2: briefing.py — report(envelope)·png_paths 캡처

**Files:** Modify `backend/app/briefing.py` (276~366행 캡처/반환부, 205~213 `_summarize_decision`, 216~240 `_latest_png`)

- [ ] **Step 1:** 캡처 dict를 `{"report": None}`로 바꾸고, `_capturing_gen`이 envelope(dict, "blocks" 보유)면 `captured["report"]=res`. 반환 `out`에 `report` 포함, 하위호환으로 `out["sections"]=report.get("legacy")` 동시 노출.
- [ ] **Step 2:** `png_paths` 추가 — `_latest_png(slot)`에 더해 장중은 `*_page*.png` 다중 매칭 함수 `_latest_png_set(slot)` 구현, `out["png_paths"]=[...]`(없으면 `[png_path]`).
```python
def _latest_png_set(slot: str) -> list[str]:
    import glob as _g
    out_root = SITELE_DIR / "output"
    pats = [str(out_root / "*" / f"*{slot}*_page*.png"), str(out_root / "*" / f"hanwha_{slot}_*.png")]
    files = []
    for p in pats:
        files.extend(_g.glob(p))
    files = sorted(set(files), key=os.path.getmtime, reverse=True)
    # 같은 생성배치(page1~3) 우선: page 토큰 보유분 그룹화
    pages = [f for f in files if "_page" in f][:3]
    return [os.path.abspath(f) for f in (pages or files[:1])]
```
- [ ] **Step 3:** `_summarize_decision`을 envelope(`title`/`stance`) 우선으로 갱신(없으면 기존 sections 호환).
- [ ] **Step 4: 검증** — 재시작 후 `curl -s -m 120 -X POST http://127.0.0.1:8000/api/briefing/close` 트리거 → `curl .../close/status` 응답에 `report.blocks`(5개)·`report.legacy`·`png_paths` 존재 확인.
- [ ] **Step 5: 체크포인트.**

> 참고: 엔드포인트 `/api/briefing/{slot}`·`/status`·`/png`는 `backend/app/main.py`에 존재. status가 run_briefing 결과를 그대로 직렬화하는지 확인하고, 아니면 `report`/`png_paths`를 통과시키도록 1~2줄 보완.

---

## Phase C — PNG 재디자인

> 두 렌더러는 기존 파일이 큼 → 각 task Step 1에서 **해당 파일을 먼저 Read** 후 편집. 데이터 계약만 고정한다.

### Task C1: 장전/장마감 1p PNG (envelope 렌더)

**Files:** Modify `backend/sitele/hanwha_report_renderer.py`, `backend/sitele/hanwha_report_template.html`

- [ ] **Step 1:** `hanwha_report_renderer.py` Read. `render_hanwha_report(slot, sections, market_data)` 시그니처 유지하되, `sections`가 envelope면 `sections["blocks"]`·`headline`·`persona`·`stance`를 템플릿 `window.reportData`로 주입(envelope 아니면 legacy 경로 유지 — 하위호환).
- [ ] **Step 2:** `hanwha_report_template.html` 재디자인 — 한화 웜다크(주황 #F37321 + warm brown + beige; 프로젝트 메모리 팔레트 준수). 영역: 헤더(persona 배지·title·stance 컬러칩·날짜) / headline 콜아웃 / 블록 그리드(paragraph·bullets·kv 분기 렌더, `report_schema` 라벨 사용) / 하단 핵심 데이터(매크로/수급). `init()`가 `window.reportData.blocks`를 순회 렌더하도록 JS 작성.
- [ ] **Step 3: 검증** — `python -X utf8 run_premarket.py`(발송 없음) → `output/.../hanwha_premarket_*.png` 생성·열어 블록 5개·persona·stance 표시 확인. `run_close.py` 동일.
- [ ] **Step 4: 체크포인트.**

### Task C2: 장중 3p PNG (tele 템플릿, envelope→analysis_text)

**Files:** Modify `backend/sitele/run_intraday.py`, `backend/sitele/report_renderer_tele.py`, `backend/sitele/report_template_tele.html`

- [ ] **Step 1:** `run_intraday.main`이 hanwha 대신 tele 렌더러를 쓰도록 분기 — `report_renderer_tele.render_full_report(...)` 호출. `analysis_text`는 envelope blocks(kospi_theme/kosdaq_theme/sector_rs/headlines)를 ■ 헤더형 텍스트로 조립하는 헬퍼 `_envelope_to_analysis_text(env)` 신설. 데이터(rs/sector/gainers/losers/breadth/news/kosdaq_*)는 B1 보강분 + `kang_close_data`/`auto_data_fetcher`에서 매핑. 캔들(`generate_candle_tele.generate`)이 있으면 KOSPI/KOSDAQ 차트 생성.
- [ ] **Step 2:** `report_template_tele.html` 톤을 한화 웜다크로 정렬(현재 라이트/인디고 계열 → 팔레트 맞춤), 단 3페이지 구조·차트 영역 유지.
- [ ] **Step 3: 검증** — `python -X utf8 run_intraday.py` → `output/.../*_page1/2/3.png` 생성 확인. main이 page1 경로(또는 page 경로 리스트)를 반환하도록 조정.
- [ ] **Step 4: 체크포인트.**

---

## Phase D — 프론트엔드

### Task D1: envelope 타입

**Files:** Modify `frontend/src/components/briefing/types.ts`

- [ ] **Step 1: 추가**
```ts
export type BlockType = 'bullets' | 'paragraph' | 'kv'
export type KvItem = { k: string; v: string; tone?: 'up' | 'down' | 'neutral' }
export type ReportBlock = {
  id: string; label: string; type: BlockType
  body: string | string[] | KvItem[]
}
export type ReportEnvelope = {
  slot: SlotId; persona: string; title: string
  stance: 'RISK-ON' | 'NEUTRAL' | 'RISK-OFF'
  headline: string; blocks: ReportBlock[]; as_of?: string
  legacy?: Record<string, string>
}
```
그리고 `BriefingStatus`에 `report?: ReportEnvelope`, `png_paths?: string[]` 추가.
- [ ] **Step 2:** `npx tsc --noEmit` → 0.
- [ ] **Step 3: 체크포인트.**

### Task D2: BriefingReport 블록 렌더러 + 테스트

**Files:** Create `frontend/src/components/briefing/BriefingReport.tsx`, `BriefingReport.test.tsx`; Modify `index.ts`

- [ ] **Step 1: 실패 테스트**
```tsx
import { render, screen } from '@testing-library/react'
import { BriefingReport } from './BriefingReport'
import type { ReportEnvelope } from './types'

const env: ReportEnvelope = {
  slot: 'close', persona: '강진혁', title: '마감·수급·판단', stance: 'RISK-OFF',
  headline: '핵심 요약', blocks: [
    { id: 'wrap', label: '마감 총평', type: 'paragraph', body: '문단 내용' },
    { id: 'flows', label: '주체별 수급', type: 'kv', body: [{ k: '외국인', v: '-3,000억', tone: 'down' }] },
    { id: 'sectors', label: '주도·부진 섹터', type: 'bullets', body: ['반도체 +1%', '2차전지 -2%'] },
  ],
}

test('renders persona, stance, headline and blocks', () => {
  render(<BriefingReport report={env} generatedAt={Date.now()} />)
  expect(screen.getByText('강진혁')).toBeInTheDocument()
  expect(screen.getByText('RISK-OFF')).toBeInTheDocument()
  expect(screen.getByText('핵심 요약')).toBeInTheDocument()
  expect(screen.getByText('마감 총평')).toBeInTheDocument()
  expect(screen.getByText('문단 내용')).toBeInTheDocument()
  expect(screen.getByText('외국인')).toBeInTheDocument()
  expect(screen.getByText('반도체 +1%')).toBeInTheDocument()
})
```
- [ ] **Step 2: 실패 확인** — `npm test -- --run BriefingReport` → FAIL(모듈 없음).
- [ ] **Step 3: 구현** — `BriefingReport.tsx`: props `{ report: ReportEnvelope; generatedAt: number | null }`. 헤더(persona Badge·title·stance pill[RISK-ON=up/RISK-OFF=down/NEUTRAL=neutral 컬러]·as_of) + headline 콜아웃 + 블록 그리드. 블록 렌더 분기: paragraph=`<p>`, bullets=`<ul>`, kv=키-값 행(tone별 text-up/down/muted). 웜다크 토큰(`Card`, `rounded-card`, `text-beige/greige/muted`, `border-line`) 사용. 슬롯별 아이콘 매핑.
- [ ] **Step 4: 통과** — `npm test -- --run BriefingReport` → PASS. `index.ts`에 `export { BriefingReport } from './BriefingReport'`.
- [ ] **Step 5: 체크포인트.**

### Task D3: BriefingAgent 연동(report·persona 헤더)

**Files:** Modify `frontend/src/components/BriefingAgent.tsx`

- [ ] **Step 1:** `const sections = result?.sections` → `const report = result?.report`. 완료 블록(344~353행)에서 `<SectionCards .../>`를 `{report && <BriefingReport report={report} generatedAt={generatedAt} />}`로 교체. SectionHeader description을 슬롯 페르소나 안내로 갱신. import에 `BriefingReport` 추가, 미사용 `SectionCards` 제거.
- [ ] **Step 2:** `npx tsc --noEmit` → 0.
- [ ] **Step 3: 체크포인트.**

### Task D4: PngCard 갤러리 + 장중 KOSPI/KOSDAQ 토글

**Files:** Modify `frontend/src/components/briefing/PngCard.tsx`, `BriefingAgent.tsx`, (장중 토글) `RsQuadrantCard.tsx`/데이터 카드

- [ ] **Step 1:** `PngCard` props에 `pngUrls?: string[]` 추가 — 다중이면 세로 스택/탭으로 page1~3 표시, 단일이면 기존 동작. `BriefingAgent`에서 `result.png_paths`로 URL 배열 구성(`/api/briefing/${slot}/png?t=...` 페이지별 인덱스 파라미터 필요 시 엔드포인트 확장; 우선 단일 png_path 유지 + 다중은 후속).
- [ ] **Step 2:** 장중 슬롯일 때 RsQuadrant/Adr/Movers/News가 `rs_kospi`/`rs_kosdaq` 등 KOSPI/KOSDAQ 토글을 노출하도록 `interactive`에 이미 존재하는 `rs_kosdaq`/`kosdaq_sectors` 활용(컴포넌트에 `market: 'kospi'|'kosdaq'` 토글 상태 추가). 기존 `RsQuadrantCard`는 KOSPI/KOSDAQ 토글이 이미 있으면 재사용.
- [ ] **Step 3:** `npx tsc --noEmit` → 0, `npm test -- --run` 그린.
- [ ] **Step 4: 체크포인트.**

### Task D5: 통합 검증

- [ ] **Step 1:** 백엔드 재시작 후 세 슬롯 각각 `curl -X POST .../api/briefing/{slot}` → status에 `report.blocks`(슬롯별 라벨) 확인.
- [ ] **Step 2:** 브라우저 `127.0.0.1:5173` 시황 탭 → 슬롯 전환·생성 → persona 헤더·블록·데이터비주·PNG 표시 육안 확인.
- [ ] **Step 3:** `npx tsc --noEmit` 0, `npm test -- --run` 그린, 백엔드 `pytest tests -q` 그린.
- [ ] **Step 4: 체크포인트(최종).**

---

## Self-Review 결과

- **스펙 커버리지:** 4.1 envelope→A1, 4.2 블록→A1/A2, 4.3 백엔드→A2/A3, 4.4 LLM 유지→A3, 4.5 PNG→C1/C2, 4.6 프론트→D1~D4, 4.7 briefing 연동→B2. 누락 없음.
- **플레이스홀더:** 핵심(A1~A4·D1~D2)은 완전 코드. 렌더러/템플릿(C1·C2)·일부 배선(B2·D4)은 거대·기존 파일 의존이라 "Step 1에서 Read 후 편집" + 데이터 계약 고정 방식으로 명시(미검증 HTML 날조 방지). 실행 시 해당 파일 정독 필요.
- **타입 일관성:** `normalize_envelope`/`to_legacy`/`fallback_envelope`(A1) ↔ A3 사용 일치. `ReportEnvelope`/`ReportBlock`(D1) ↔ D2/D3 사용 일치. `SLOT_BLOCKS` id가 프롬프트(A2)·legacy 매핑(A1)·프론트 라벨(D2)에서 동일.
