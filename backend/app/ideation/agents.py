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


def sector_bull(regime: Dict[str, Any], lanes: List[Dict[str, Any]], prior: str) -> Tuple[str, Dict[str, Any]]:
    top = sorted(lanes, key=lambda l: l.get('score', 0), reverse=True)
    fb_lanes = _lane_names(top)[:2]
    fb = f"{', '.join(fb_lanes)} 레인이 뉴스·매크로와 함께 움직여 유망합니다." if fb_lanes else '유망 레인을 점검했습니다.'
    system = ('너는 Bull 섹터 리서처다. 제공된 레인 점수·뉴스·매크로 태그만 근거로 가장 유망한 섹터 '
              '레인을 주장한다. Bear의 직전 반론이 있으면 재반박한다. '
              '응답은 {"speech": "<2~3문장>", "favored_lanes": ["<섹터>", ...]} JSON 하나.')
    user = _fmt({'regime': regime.get('label'), 'lanes': lanes, 'bear_prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'favored_lanes': fb_lanes})
    return str(parsed.get('speech') or fb), {'favored_lanes': parsed.get('favored_lanes') or fb_lanes}


def sector_bear(regime: Dict[str, Any], lanes: List[Dict[str, Any]], prior: str) -> Tuple[str, Dict[str, Any]]:
    risky = sorted(lanes, key=lambda l: l.get('score', 0))[:1]
    fb_lanes = _lane_names(risky)
    fb = f"{', '.join(fb_lanes)} 레인은 과열·근거 부족 위험이 있습니다." if fb_lanes else '과열 레인을 점검했습니다.'
    system = ('너는 Bear 섹터 리서처다. 제공된 레인 점수·뉴스만 근거로 과열되었거나 근거가 약한 레인을 '
              '반박한다. Bull의 직전 주장을 구체적으로 반론한다. '
              '응답은 {"speech": "<2~3문장>", "risky_lanes": ["<섹터>", ...]} JSON 하나.')
    user = _fmt({'regime': regime.get('label'), 'lanes': lanes, 'bull_prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'risky_lanes': fb_lanes})
    return str(parsed.get('speech') or fb), {'risky_lanes': parsed.get('risky_lanes') or fb_lanes}


def research_manager(regime: Dict[str, Any], lanes: List[Dict[str, Any]], bull_hist: str, bear_hist: str) -> Tuple[str, Dict[str, Any]]:
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
    names = ', '.join(n['name'] for n in noms if n.get('name')) or '후보'
    return f"{lane_sector} 레인에서 {names}을(를) 상정합니다.", {'nominations': noms}


# ── 4단계: 3-way 리스크 토론 ────────────────────────────────────
def _timing_str(nominee: Dict[str, Any]) -> str:
    t = nominee.get('timing_signal') or {}
    return f"signal={t.get('signal')} rsi={t.get('rsi')} reason={t.get('reason')}"


def risk_aggressive(nominee: Dict[str, Any], prior: str) -> Tuple[str, Dict[str, Any]]:
    fb = f"{nominee.get('name')} 모멘텀이 살아있어 상방 여지가 있습니다."
    system = ('너는 공격적 리스크 심의역이다. 후보의 상방·모멘텀을 강조하되 타이밍 신호를 인용한다. '
              '응답은 {"speech": "<2문장>"} JSON 하나.')
    user = _fmt({'nominee': nominee.get('name'), 'timing': _timing_str(nominee), 'prior': prior})
    speech, _ = _speak_text(system, user, fb)
    return speech, {}


def risk_conservative(nominee: Dict[str, Any], prior: str) -> Tuple[str, Dict[str, Any]]:
    t = nominee.get('timing_signal') or {}
    overheated = t.get('signal') in {'wait', 'avoid'}
    fb = (f"{nominee.get('name')}은 {t.get('reason') or '과열'} — 추격매수 리스크가 있습니다."
          if overheated else f"{nominee.get('name')}의 하방·변동성을 점검해야 합니다.")
    system = ('너는 보수적 리스크 심의역이다. 과열·추격매수·하방을 타이밍 신호(RSI/MA20)를 인용해 경고한다. '
              '응답은 {"speech": "<2문장>", "block": <true/false>} JSON 하나.')
    user = _fmt({'nominee': nominee.get('name'), 'timing': _timing_str(nominee), 'prior': prior})
    parsed, _ = _speak_json(system, user, fallback={'speech': fb, 'block': overheated})
    return str(parsed.get('speech') or fb), {'block': bool(parsed.get('block', overheated))}


def risk_neutral(nominee: Dict[str, Any], prior: str) -> Tuple[str, Dict[str, Any]]:
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
def pm_chair(regime: Dict[str, Any], winning_lanes: List[str], nominees: List[Dict[str, Any]], risk_notes: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
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
