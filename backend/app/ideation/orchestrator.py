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
