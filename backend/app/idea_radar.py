from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

DATA_DIR = Path(__file__).resolve().parents[1] / 'data'
HISTORY_PATH = DATA_DIR / 'idea_history.json'

FACTOR_WEIGHTS: Dict[str, float] = {
    'chart': 0.18,
    'supply_demand': 0.17,
    'news': 0.18,
    'macro': 0.17,
    'valuation': 0.14,
    'risk': 0.16,
}

THEME_SEEDS: List[Dict[str, Any]] = [
    {
        'theme': '반도체 AI 인프라',
        'sector': '반도체',
        'macro_tags': ['risk-on', '원화 안정', 'AI capex'],
        'symbols': [
            {'symbol': '000660', 'name': 'SK하이닉스', 'chart': 86, 'supply_demand': 83, 'news': 87, 'macro': 81, 'valuation': 68, 'risk': 63},
            {'symbol': '005930', 'name': '삼성전자', 'chart': 76, 'supply_demand': 72, 'news': 75, 'macro': 78, 'valuation': 74, 'risk': 70},
        ],
    },
    {
        'theme': '전력기기·전력망',
        'sector': '전력기기',
        'macro_tags': ['전력수요', '인프라 투자', '미국 CAPEX'],
        'symbols': [
            {'symbol': '267260', 'name': 'HD현대일렉트릭', 'chart': 88, 'supply_demand': 78, 'news': 82, 'macro': 86, 'valuation': 62, 'risk': 58},
            {'symbol': '010120', 'name': 'LS ELECTRIC', 'chart': 79, 'supply_demand': 74, 'news': 77, 'macro': 83, 'valuation': 66, 'risk': 67},
        ],
    },
    {
        'theme': '방산·우주',
        'sector': '방산',
        'macro_tags': ['지정학', '수출 수주', '국방 예산'],
        'symbols': [
            {'symbol': '012450', 'name': '한화에어로스페이스', 'chart': 84, 'supply_demand': 76, 'news': 85, 'macro': 80, 'valuation': 60, 'risk': 57},
            {'symbol': '079550', 'name': 'LIG넥스원', 'chart': 72, 'supply_demand': 69, 'news': 74, 'macro': 79, 'valuation': 70, 'risk': 65},
        ],
    },
    {
        'theme': '조선·해양플랜트',
        'sector': '조선',
        'macro_tags': ['달러 매출', '선가', 'LNG'],
        'symbols': [
            {'symbol': '042660', 'name': '한화오션', 'chart': 81, 'supply_demand': 71, 'news': 80, 'macro': 76, 'valuation': 58, 'risk': 54},
            {'symbol': '009540', 'name': 'HD한국조선해양', 'chart': 75, 'supply_demand': 73, 'news': 76, 'macro': 78, 'valuation': 64, 'risk': 62},
        ],
    },
    {
        'theme': '자동차·주주환원',
        'sector': '자동차',
        'macro_tags': ['환율 민감', '밸류업', '배당'],
        'symbols': [
            {'symbol': '005380', 'name': '현대차', 'chart': 70, 'supply_demand': 68, 'news': 72, 'macro': 66, 'valuation': 78, 'risk': 73},
            {'symbol': '000270', 'name': '기아', 'chart': 69, 'supply_demand': 67, 'news': 70, 'macro': 65, 'valuation': 80, 'risk': 74},
        ],
    },
]


def _today() -> dt.date:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()


def _iso_now() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).isoformat(timespec='seconds')


def _stable_jitter(symbol: str, factor: str, scale: int = 5) -> int:
    h = hashlib.sha256(f'{symbol}:{factor}:{_today().isoformat()}'.encode('utf-8')).hexdigest()
    return int(h[:2], 16) % (scale * 2 + 1) - scale


def _clamp(value: float, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, int(round(value))))


def _weighted_score(scores: Dict[str, int]) -> int:
    return _clamp(sum(scores[k] * w for k, w in FACTOR_WEIGHTS.items()))


def _factor_scores(seed: Dict[str, Any], live: Optional[Dict[str, int]] = None) -> Dict[str, int]:
    symbol = str(seed['symbol'])
    if live:
        # 실데이터 점수 우선, 누락 팩터는 시드+jitter 폴백
        return {factor: _clamp(live.get(factor, int(seed[factor]) + _stable_jitter(symbol, factor)))
                for factor in FACTOR_WEIGHTS}
    return {factor: _clamp(int(seed[factor]) + _stable_jitter(symbol, factor)) for factor in FACTOR_WEIGHTS}


def _live_factor_scores(seed: Dict[str, Any], regime_tilt: str) -> Tuple[Dict[str, int], Dict[str, str]]:
    """idea_engine 수집 함수로 6개 팩터를 실데이터 0~100 점수화. 팩터별 실패 시 시드 폴백.

    반환: (scores, sources) — sources[factor] ∈ {'live','seed'}
    """
    code = str(seed['symbol'])
    name = str(seed.get('name') or code)
    scores: Dict[str, int] = {}
    sources: Dict[str, str] = {}

    try:
        from . import idea_engine as ie
    except Exception:
        return {}, {f: 'seed' for f in FACTOR_WEIGHTS}

    def _seed(factor: str) -> int:
        return _clamp(int(seed[factor]))

    # OHLCV 는 chart·risk 두 팩터에서 공용 → 한 번만 수집
    try:
        ohlcv = ie._collect_ohlcv(code)
    except Exception:
        ohlcv = None

    # ── chart: 20/60일 모멘텀 + 52주 고가 근접도 ──
    try:
        if ohlcv:
            r20 = ohlcv.get('ret_20d_pct'); r60 = ohlcv.get('ret_60d_pct')
            close = ohlcv.get('close'); hi = ohlcv.get('high_period'); lo = ohlcv.get('low_period')
            mom = 50.0 + (r20 or 0.0) * 1.5 + (r60 or 0.0) * 0.5
            pos52 = 50.0
            if close and hi and lo and hi > lo:
                pos52 = (close - lo) / (hi - lo) * 100.0
            scores['chart'] = _clamp(0.6 * mom + 0.4 * pos52); sources['chart'] = 'live'
    except Exception:
        pass

    # ── supply_demand: 외국인+기관 순매수(억원) ──
    try:
        flows = ie._collect_investor_flows(code)
        if flows:
            net = (flows.get('외국인') or 0.0) + (flows.get('기관합계') or 0.0)
            scores['supply_demand'] = _clamp(50.0 + net / 40.0); sources['supply_demand'] = 'live'
    except Exception:
        pass

    # ── news: 건수 + 최신성 ──
    try:
        news = ie._collect_news(name)
        if news:
            cnt = len(news)
            recent_bonus = 12 if any('hour' in (n.get('published') or '').lower()
                                     or 'min' in (n.get('published') or '').lower() for n in news) else 0
            scores['news'] = _clamp(40 + cnt * 8 + recent_bonus); sources['news'] = 'live'
    except Exception:
        pass

    # ── macro: 시장 regime tilt ──
    tilt_base = {'risk-on': 72, 'neutral': 55, 'risk-off': 42}.get(regime_tilt, 55)
    # 시드 macro 와 평균해 테마별 미세 차등 유지
    scores['macro'] = _clamp(0.7 * tilt_base + 0.3 * _seed('macro')); sources['macro'] = 'live'

    # ── valuation: PBR/PER 밴드(저평가 → 고득점) ──
    try:
        fund = ie._collect_fundamental(code)
        if fund and (fund.get('PBR') is not None or fund.get('PER') is not None):
            pbr = fund.get('PBR'); per = fund.get('PER')
            parts = []
            if pbr is not None:
                parts.append(_clamp(90 - (pbr - 0.8) * 40))   # PBR 0.8→90, 1.8→50, 2.8→10
            if per is not None and per > 0:
                parts.append(_clamp(90 - (per - 8) * 2.2))     # PER 8→90, 25→52
            if parts:
                scores['valuation'] = _clamp(sum(parts) / len(parts)); sources['valuation'] = 'live'
    except Exception:
        pass

    # ── risk: 변동성(모멘텀 진폭) + 공매도 압력 차감(가용 시) ──
    try:
        base_risk = 70.0
        if ohlcv:
            base_risk -= abs(ohlcv.get('ret_20d_pct') or 0.0) * 0.5
        short = ie._collect_shorting(code)
        if short:
            # 잔고/비중류 필드가 있으면 과열로 보고 차감(best-effort)
            ratio = next((v for k, v in short.items() if isinstance(v, (int, float)) and ('비중' in str(k) or '잔고' in str(k))), None)
            if ratio:
                base_risk -= min(15.0, float(ratio))
            sources['risk'] = 'live'
        if ohlcv or short:
            scores['risk'] = _clamp(base_risk)
            sources.setdefault('risk', 'live')
    except Exception:
        pass

    # 누락 팩터는 시드로 채우고 source=seed
    for f in FACTOR_WEIGHTS:
        if f not in scores:
            scores[f] = _seed(f)
            sources.setdefault(f, 'seed')
    return scores, sources


def _compute_timing_signal(code: str, ohlcv: Optional[dict] = None) -> dict:
    """RSI(14) · 20일 이평 위치로 진입 타이밍 신호(enter/wait/avoid) 생성."""
    try:
        from pykrx import stock as krx
        start = (_today() - dt.timedelta(days=60)).strftime("%Y%m%d")
        end = _today().strftime("%Y%m%d")
        df = krx.get_market_ohlcv_by_date(start, end, code)
        if df is None or len(df) < 15:
            raise ValueError("insufficient data")
        closes = list(df['종가'].astype(float))
        # RSI(14)
        diffs = [closes[i] - closes[i - 1] for i in range(len(closes) - 14, len(closes))]
        gains = [max(d, 0) for d in diffs]
        losses = [max(-d, 0) for d in diffs]
        avg_g = sum(gains) / 14
        avg_l = sum(losses) / 14
        rsi = round(100 - (100 / (1 + avg_g / avg_l)) if avg_l > 0 else 100.0, 1)
        # MA20
        ma_window = closes[-min(20, len(closes)):]
        ma20 = sum(ma_window) / len(ma_window)
        ma20_pct = round((closes[-1] / ma20 - 1) * 100, 1) if ma20 > 0 else 0.0
        # Signal
        if rsi > 70 or ma20_pct > 10:
            signal = 'wait'
            reason = f'RSI {rsi} 과매수' if rsi > 70 else f'20일 이평 +{ma20_pct:.1f}% 과열'
        elif rsi < 30 or ma20_pct < -15:
            signal = 'avoid'
            reason = f'RSI {rsi} 과매도·추세 붕괴'
        else:
            signal = 'enter'
            reason = f'RSI {rsi} · 이평 대비 {ma20_pct:+.1f}%'
        return {'signal': signal, 'rsi': rsi, 'ma20_pct': ma20_pct, 'reason': reason}
    except Exception:
        if ohlcv:
            r20 = float(ohlcv.get('ret_20d_pct') or 0.0)
            sig = 'wait' if r20 > 12 else ('avoid' if r20 < -15 else 'enter')
            return {'signal': sig, 'rsi': None, 'ma20_pct': round(r20, 1),
                    'reason': f'20일 수익률 {r20:+.1f}%'}
        return {'signal': 'enter', 'rsi': None, 'ma20_pct': None, 'reason': None}


def _build_sector_rank() -> List[Dict[str, Any]]:
    """auto_data_fetcher 실시간 섹터 데이터로 섹터 매력도 순위 산출."""
    try:
        import sys, os as _os
        _sitele = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)), 'sitele')
        if _sitele not in sys.path:
            sys.path.insert(0, _sitele)
        import auto_data_fetcher as _adf
        data = _adf.get_complete_report_data()
        sectors_raw = data.get('sectorReturns') or []
        if not sectors_raw:
            raise ValueError('no sector data')
        result = []
        for s in sectors_raw:
            name = str(s.get('sector') or s.get('name') or '').strip()
            if not name:
                continue
            chg = float(s.get('change') or 0)
            score = max(0, min(100, int(50 + chg * 8)))
            result.append({
                'sector': name, 'score': score, 'change': round(chg, 2),
                'foreign_flow': 'buy' if chg > 0.3 else ('sell' if chg < -0.3 else 'neutral'),
            })
        result.sort(key=lambda x: x['score'], reverse=True)
        return result[:10]
    except Exception:
        return [{'sector': t['sector'], 'score': 60, 'change': 0.0, 'foreign_flow': 'neutral'}
                for t in THEME_SEEDS[:6]]


def _build_timing_map(picks: List[Dict[str, Any]]) -> Dict[str, dict]:
    """top_picks 종목별 타이밍 신호 병렬 계산."""
    result: Dict[str, dict] = {}
    def _one(pick: Dict[str, Any]) -> Tuple[str, dict]:
        sym = str(pick['symbol'])
        return sym, _compute_timing_signal(sym)
    with ThreadPoolExecutor(max_workers=5) as ex:
        for sym, sig in ex.map(_one, picks):
            result[sym] = sig
    return result


def _evidence_for(theme: Dict[str, Any], item: Dict[str, Any], scores: Dict[str, int]) -> List[Dict[str, Any]]:
    return [
        {'factor': 'chart', 'title': '가격/차트', 'detail': f"RS·추세·거래대금 조합 점수 {scores['chart']}점. 단독 RS가 아니라 거래대금과 추세 지속성을 함께 봅니다."},
        {'factor': 'supply_demand', 'title': '수급', 'detail': f"외국인/기관 수급 연속성 프록시 {scores['supply_demand']}점. 추세 확인용 신호입니다."},
        {'factor': 'news', 'title': '뉴스/이벤트', 'detail': f"최근 {theme['theme']} 관련 뉴스·정책·수주 이벤트 강도 {scores['news']}점."},
        {'factor': 'macro', 'title': '매크로 궁합', 'detail': f"{', '.join(theme['macro_tags'])} 환경과의 적합도 {scores['macro']}점."},
        {'factor': 'valuation', 'title': '밸류/펀더멘털', 'detail': f"밸류 부담과 실적 설명 가능성을 반영한 sanity check {scores['valuation']}점."},
        {'factor': 'risk', 'title': '리스크 통과', 'detail': f"과열·악재·데이터 커버리지 리스크를 차감한 방어 점수 {scores['risk']}점."},
    ]


def _pick(theme: Dict[str, Any], item: Dict[str, Any],
          live_map: Optional[Dict[str, Dict[str, int]]] = None,
          sources_map: Optional[Dict[str, Dict[str, str]]] = None) -> Dict[str, Any]:
    sym = str(item['symbol'])
    live = (live_map or {}).get(sym)
    scores = _factor_scores(item, live)
    discovery = _clamp((scores['chart'] + scores['supply_demand'] + scores['news']) / 3)
    conviction = _clamp((scores['macro'] + scores['valuation'] + scores['risk']) / 3)
    total = _weighted_score(scores)
    status = 'research_note'
    factor_sources = (sources_map or {}).get(sym) or {f: 'seed' for f in FACTOR_WEIGHTS}
    return {
        'factor_sources': factor_sources,
        'pick_id': f"{item['symbol']}-{_today().isoformat()}",
        'symbol': item['symbol'],
        'name': item['name'],
        'theme': theme['theme'],
        'sector': theme['sector'],
        'score': total,
        'discovery_score': discovery,
        'conviction_score': conviction,
        'status': status,
        'horizon_months': 3,
        'thesis': f"{item['name']}은(는) {theme['theme']} 테마 내에서 단기 모멘텀과 중기 설명력이 동시에 확인되는 리서치 후보입니다.",
        'why_now': f"차트·수급·뉴스가 동시에 개선되고, {', '.join(theme['macro_tags'])} 매크로 맥락이 테마 지속성을 보강합니다.",
        'factor_scores': scores,
        'evidence': _evidence_for(theme, item, scores),
        'counter_evidence': [
            '단기 급등 후 거래대금이 식으면 thesis 확인 전 추격매수 리스크가 큽니다.',
            '실적/수주/정책 뉴스가 후속 확인되지 않으면 테마 지속성이 약해질 수 있습니다.',
            '시장 위험회피와 환율/금리 급변 시 멀티플 압박을 재점검해야 합니다.',
        ],
        'checklist': [
            '최근 5거래일 거래대금이 테마 내 상위권으로 유지되는지 확인',
            '외국인/기관 순매수의 연속성과 단절 여부 확인',
            '뉴스/공시 이벤트가 실제 실적 추정치로 연결되는지 확인',
            '3개월 추적 기간 동안 thesis 훼손 뉴스 발생 여부 점검',
        ],
        'actions': ['save_history', 'single_idea', 'backtest', 'committee'],
    }


# 키워드 의도 파싱: "반도체 제외 타섹터" 같은 부정(제외) 의도를 인식한다.
_EXCLUDE_MARKERS = ('제외', '제외하고', '말고', '빼고', '빼', '외에', '외엔', '아닌', '없는', 'except', 'not', 'no')
_KW_STOPWORDS = {
    '타섹터', '다른', '딴', '섹터', '업종', '종목', '추천', '추천해줘', '무엇', '무엇을', '뭐', '뭘',
    '어떤', '어느', '보는게', '보는', '볼까', '봐야', '좋을까', '좋은', '좋아', '할까', '하면', '하나',
    '것', '게', '들', '관련', '대해', '대한', '쪽', '주는', '주식', '투자', '아이디어', '알려줘', '골라줘',
}


def _parse_keyword_intent(keywords: str) -> Tuple[List[str], List[str]]:
    """(includes, excludes). 예) '반도체 제외 타섹터' → includes=[], excludes=['반도체'].

    부정 마커(제외/말고/빼고 등)가 있으면 마커 앞 내용어는 제외 대상, 마커 뒤 내용어는
    포함 대상으로 간주한다. 마커가 없으면 모든 내용어가 포함(기존 동작).
    """
    toks = [w.strip().lower() for w in re.split(r'[\s,?!.·]+', str(keywords or '')) if w.strip()]
    has_marker = any(any(m in t for m in _EXCLUDE_MARKERS) for t in toks)
    includes: List[str] = []
    excludes: List[str] = []
    seen_marker = False
    for t in toks:
        if any(m in t for m in _EXCLUDE_MARKERS):
            seen_marker = True
            continue
        if t in _KW_STOPWORDS or len(t) < 2:
            continue
        if has_marker and not seen_marker:
            excludes.append(t)   # 마커 앞 토큰 = 제외 대상
        else:
            includes.append(t)
    return includes, excludes


def _theme_hay(theme: Dict[str, Any]) -> str:
    return ' '.join([theme['theme'], theme['sector'], *theme['macro_tags']]).lower()


def _matches_keywords(theme: Dict[str, Any], keywords: str) -> bool:
    includes, excludes = _parse_keyword_intent(keywords)
    haystack = _theme_hay(theme)
    if excludes and any(x in haystack for x in excludes):
        return False  # 사용자가 제외 요청한 섹터는 탈락
    if not includes:
        return True   # 제외만 있거나 키워드 없음 → 나머지 전부 통과
    return any(inc in haystack for inc in includes)


def _select_themes(keywords: str) -> List[Dict[str, Any]]:
    """키워드 의도(포함/제외)를 반영해 테마 레인을 선택한다.

    제외가 우선: 제외 섹터를 먼저 제거하고, 그 다음 포함어로 좁힌다. 포함어가 아무 것도
    못 맞추면(예: '다른거' 같은 일반어) 제외만 적용된 풀을 그대로 반환한다. 모두 비면 전체.
    """
    includes, excludes = _parse_keyword_intent(keywords)
    pool = list(THEME_SEEDS)
    if excludes:
        pool = [t for t in pool if not any(x in _theme_hay(t) for x in excludes)]
    if includes:
        matched = [t for t in pool if any(inc in _theme_hay(t) for inc in includes)]
        if matched:
            return matched
    return pool or list(THEME_SEEDS)


# ---------------------------------------------------------------------------
# News-flow top-down pipeline: Macro ? Sector ? Stock
# ---------------------------------------------------------------------------

def _news_items_for_pick(pick: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Collect compact news/event evidence for a candidate without making it mandatory."""
    items: List[Dict[str, Any]] = []
    try:
        from .data_loader import load_news
        for n in load_news():
            symbols = [str(x) for x in (n.get('symbols') or [])]
            if str(pick.get('symbol')) in symbols:
                items.append({
                    'title': n.get('title'),
                    'source': n.get('source') or 'sample_news',
                    'published_at': n.get('published_at'),
                    'symbols': symbols,
                    'stage': 'stock',
                })
    except Exception:
        pass

    # Include first live/template news evidence if enrichment already attached it.
    for ev in pick.get('evidence') or []:
        title = str(ev.get('title') or ev.get('claim') or '')
        detail = str(ev.get('detail') or ev.get('value') or '')
        if ('??' in title or 'News' in title or 'Google' in str(ev.get('source') or '')) and (title or detail):
            items.append({
                'title': detail or title,
                'source': ev.get('source') or 'candidate_evidence',
                'published_at': None,
                'symbols': [pick.get('symbol')],
                'stage': 'stock',
            })
            break
    return items[:4]


def _build_newsflow_pipeline(
    market_regime: Dict[str, Any],
    themes: List[Dict[str, Any]],
    top_picks: List[Dict[str, Any]],
    sector_rank: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Build a reader-facing top-down flow from news/macro context to candidates."""
    macro_keywords = market_regime.get('news_keywords') or []
    macro_points = market_regime.get('macro_points') or market_regime.get('rationale') or []
    macro_flow = {
        'stage': 'macro',
        'label': market_regime.get('label') or market_regime.get('tilt') or 'neutral',
        'score': market_regime.get('score'),
        'summary': market_regime.get('summary') or '?????? ??? ???? ?? ??? ?????.',
        'keywords': macro_keywords[:8],
        'signals': macro_points[:6],
        'source': market_regime.get('source') or 'rule_based',
    }

    rank_by_sector = {str(s.get('sector')): s for s in sector_rank}
    sector_flow: List[Dict[str, Any]] = []
    for theme in themes[:8]:
        rank = rank_by_sector.get(str(theme.get('sector')), {})
        reps = theme.get('representatives') or []
        news_pull = max([int((p.get('factor_scores') or {}).get('news', 0)) for p in top_picks if p.get('sector') == theme.get('sector')] or [0])
        sector_flow.append({
            'stage': 'sector',
            'sector': theme.get('sector'),
            'theme': theme.get('theme'),
            'score': theme.get('score'),
            'news_score': news_pull,
            'change': rank.get('change'),
            'foreign_flow': rank.get('foreign_flow'),
            'macro_tags': theme.get('macro_tags') or [],
            'why': theme.get('commentary') or f"{theme.get('theme')} ??? ??? ??? ??? ?????.",
            'representatives': reps[:4],
        })

    stock_candidates: List[Dict[str, Any]] = []
    news_flow: List[Dict[str, Any]] = []
    for pick in top_picks:
        route = [
            macro_flow['label'],
            pick.get('sector'),
            pick.get('theme'),
            f"{pick.get('name')}({pick.get('symbol')})",
        ]
        items = _news_items_for_pick(pick)
        news_flow.extend(items)
        stock_candidates.append({
            'stage': 'stock',
            'symbol': pick.get('symbol'),
            'name': pick.get('name'),
            'sector': pick.get('sector'),
            'theme': pick.get('theme'),
            'score': pick.get('score'),
            'discovery_score': pick.get('discovery_score'),
            'conviction_score': pick.get('conviction_score'),
            'timing_signal': pick.get('timing_signal'),
            'route': route,
            'why_now': pick.get('why_now'),
            'thesis': pick.get('thesis'),
            'factor_scores': pick.get('factor_scores') or {},
            'evidence': items or (pick.get('evidence') or [])[:2],
            'actions': pick.get('actions') or ['save_history', 'single_idea', 'backtest', 'committee'],
        })

    # Deduplicate news by title/source while preserving order.
    seen = set()
    deduped_news = []
    for item in news_flow:
        key = (item.get('title'), item.get('source'))
        if key in seen or not item.get('title'):
            continue
        seen.add(key)
        deduped_news.append(item)

    return {
        'mode': 'newsflow_topdown',
        'stages': ['Macro', 'Sector', 'Stock'],
        'macro': macro_flow,
        'sectors': sector_flow,
        'stock_candidates': stock_candidates,
        'news_flow': deduped_news[:12],
        'summary': f"{macro_flow['label']} ???? ?? ??? ? ?? ?? ? ?? ?? ??? ?? {len(stock_candidates)}?? ??????.",
    }


def _build_committee_minutes(market_regime: Dict[str, Any], newsflow: Dict[str, Any]) -> List[Dict[str, str]]:
    """Return result-grounded committee notes for the frontend.

    These are not simulated live chat messages; they summarize the actual radar output.
    When the market regime was generated by MiMo, the macro note carries that source.
    """
    macro = newsflow.get('macro') or {}
    sectors = newsflow.get('sectors') or []
    candidates = newsflow.get('stock_candidates') or []
    top_sector = sectors[0] if sectors else {}
    top_pick = candidates[0] if candidates else {}
    return [
        {
            'agent': 'Macro PM',
            'stage': 'macro',
            'text': str(macro.get('summary') or market_regime.get('summary') or '매크로 국면을 정리했습니다.'),
            'source': str(macro.get('source') or market_regime.get('source') or 'rules'),
        },
        {
            'agent': 'Sector Analyst',
            'stage': 'sector',
            'text': (
                f"{top_sector.get('sector') or top_sector.get('theme') or '상위 섹터'} 레인을 우선 검토 대상으로 올렸습니다. "
                f"{top_sector.get('why') or ''}"
            ).strip(),
            'source': 'radar:sector_flow',
        },
        {
            'agent': 'Stock Picker',
            'stage': 'stock',
            'text': (
                f"{top_pick.get('name') or '상위 후보'}({top_pick.get('symbol') or '-'})를 후보로 상정했습니다. "
                f"{top_pick.get('why_now') or top_pick.get('thesis') or ''}"
            ).strip(),
            'source': str(top_pick.get('evidence_source') or 'radar:stock_candidates'),
        },
        {
            'agent': 'PM Chair',
            'stage': 'decision',
            'text': str(newsflow.get('summary') or f"후보 {len(candidates)}개를 회의 결과로 정리했습니다."),
            'source': str(market_regime.get('source') or 'rules'),
        },
    ]


# ---------------------------------------------------------------------------
# Market Regime — 실데이터 스냅샷 → 규칙기반 근거 → LLM 서술(graceful degrade)
# ---------------------------------------------------------------------------

_REGIME_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_REGIME_TTL_SEC = 600  # 10분: 같은 시간대 반복 조회 시 KPI/LLM 재호출 방지


def _num(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _live_macro_snapshot() -> Dict[str, Any]:
    """KPI 행과 동일 소스(price_service + yfinance)에서 매크로 스냅샷을 best-effort 수집.

    네트워크/소스 실패는 개별적으로 흡수하고 가능한 값만 채운다. get_yf_metric은
    6초 타임아웃 + 캐시 + stale 폴백이 있어 호출 비용이 제한된다.
    """
    snap: Dict[str, Any] = {'kospi': None, 'kosdaq': None, 'usdkrw': None,
                            'vix': None, 'wti': None, 'gold': None, 'ok': False}
    try:
        from .price_service import get_index
        from .market_table import get_yf_metric

        def _idx(name: str) -> Dict[str, Optional[float]]:
            try:
                q = get_index(name)
                return {'value': _num(q.get('price')), 'change': _num(q.get('change_pct'))}
            except Exception:
                return {'value': None, 'change': None}

        def _yf(ticker: str) -> Dict[str, Optional[float]]:
            try:
                m = get_yf_metric(ticker) or {}
                return {'value': _num(m.get('value')), 'change': _num(m.get('change'))}
            except Exception:
                return {'value': None, 'change': None}

        snap.update({
            'kospi': _idx('KOSPI'),
            'kosdaq': _idx('KOSDAQ'),
            'usdkrw': _yf('USDKRW=X'),
            'vix': _yf('^VIX'),
            'wti': _yf('CL=F'),
            'gold': _yf('GC=F'),
            'ok': True,
        })
    except Exception:
        pass
    return snap


def _regime_from_rules(snap: Dict[str, Any], theme_spread: int) -> Dict[str, Any]:
    """실데이터로 risk-on/off 성향과 '선별적(selective)' 여부를 규칙으로 판정.

    근거(data_basis)에는 판정에 실제로 쓰인 수치를 그대로 적어 투명하게 노출한다.
    LLM 미가용 시 이 결과가 최종값이 되고, 가용 시 LLM 서술의 입력/검증 기준이 된다.
    """
    vix = _num((snap.get('vix') or {}).get('value'))
    fx_chg = _num((snap.get('usdkrw') or {}).get('change'))
    kospi_chg = _num((snap.get('kospi') or {}).get('change'))
    kosdaq_chg = _num((snap.get('kosdaq') or {}).get('change'))

    basis: List[str] = []
    votes = 0.0
    total = 0.0

    if vix is not None:
        total += 1
        if vix < 18:
            votes += 1; basis.append(f'VIX {vix:.1f} (<18) → 변동성 안정, 위험선호 우호')
        elif vix > 25:
            basis.append(f'VIX {vix:.1f} (>25) → 변동성 경계, 위험회피')
        else:
            votes += 0.5; basis.append(f'VIX {vix:.1f} → 중립 변동성')

    if fx_chg is not None:
        total += 1
        if abs(fx_chg) < 0.4:
            votes += 1; basis.append(f'USD/KRW {fx_chg:+.2f}% → 원화 안정')
        elif fx_chg > 0.8:
            basis.append(f'USD/KRW {fx_chg:+.2f}% → 원화 약세 압력, 위험회피')
        else:
            votes += 0.5; basis.append(f'USD/KRW {fx_chg:+.2f}% → 환율 변동 보통')

    idx_changes = [c for c in (kospi_chg, kosdaq_chg) if c is not None]
    if idx_changes:
        total += 1
        avg = sum(idx_changes) / len(idx_changes)
        if avg > 0.1:
            votes += 1; basis.append(f'지수 평균 {avg:+.2f}% → 시장 상방')
        elif avg < -0.3:
            basis.append(f'지수 평균 {avg:+.2f}% → 시장 약세')
        else:
            votes += 0.5; basis.append(f'지수 평균 {avg:+.2f}% → 보합권')

    ratio = (votes / total) if total else 0.5
    if ratio >= 0.66:
        tilt = 'risk-on'
    elif ratio <= 0.34:
        tilt = 'risk-off'
    else:
        tilt = 'neutral'

    selective = theme_spread >= 6
    basis.append(
        f'테마 컴포짓 점수 분산 {theme_spread}p → '
        + ('테마 간 차별화가 커 지수보다 선별적 접근 유리' if selective else '테마 간 편차가 작음')
    )

    label = (('Selective ' if selective else '') + tilt)
    label = label[:1].upper() + label[1:]

    if not total:
        basis.insert(0, '실시간 매크로 미수집 → 테마 분산만으로 보수적 판정')

    tilt_summary = {
        'risk-on': '변동성·환율·지수가 위험선호에 우호적입니다.',
        'risk-off': '변동성·환율 부담으로 방어적 접근이 필요한 국면입니다.',
        'neutral': '매크로 신호가 엇갈려 방향성보다 종목/테마 선별이 중요합니다.',
    }[tilt]
    selective_note = (
        ' 다만 테마 간 점수 편차가 커, 지수 베팅보다 테마 확산·뉴스·수급 연속성이 더 중요합니다.'
        if selective else ''
    )

    macro_points: List[str] = []
    if vix is not None:
        macro_points.append(f'VIX {vix:.1f} — 변동성 {"안정" if vix < 18 else ("경계" if vix > 25 else "중립")}')
    if fx_chg is not None:
        macro_points.append(f'USD/KRW {fx_chg:+.2f}% — 환율/금리 급변 여부 확인')
    macro_points.append('AI·인프라 CAPEX 지속 여부')
    macro_points.append('정책/수주 뉴스 민감도')

    return {
        'label': label,
        'summary': tilt_summary + selective_note,
        'rationale': list(basis),
        'data_basis': list(basis),
        'macro_points': macro_points,
        'inputs': {
            'vix': vix, 'usdkrw_change_pct': fx_chg,
            'kospi_change_pct': kospi_chg, 'kosdaq_change_pct': kosdaq_chg,
            'theme_spread': theme_spread,
        },
        'tilt': tilt,
        'selective': selective,
        'source': 'rules',
    }


def _regime_with_llm(rule_regime: Dict[str, Any], themes: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """규칙판정 결과 + 테마 점수를 LLM(MiMo→OpenAI→Anthropic)에 주고 국면 서술을 생성.

    LLM은 주어진 수치만 근거로 삼도록 지시한다. 키 없음/파싱 실패 등 어떤 사유로든
    실패하면 None 을 반환해 호출부가 규칙 결과로 graceful degrade 한다.
    """
    try:
        from .idea_engine import _call_llm
    except Exception:
        return None

    top = [{'theme': t['theme'], 'score': t['score'], 'macro_tags': t['macro_tags']} for t in themes[:5]]
    payload = {
        'rule_label': rule_regime['label'],
        'tilt': rule_regime['tilt'],
        'selective': rule_regime['selective'],
        'macro_inputs': rule_regime['inputs'],
        'data_basis': rule_regime['data_basis'],
        'top_themes': top,
    }
    system = (
        '너는 한국 주식 운용 데스크의 매크로 전략가다. 아래 JSON에 담긴 실시간 지표와 '
        '테마 컴포짓 점수만을 근거로 시장 국면(market regime)을 한국어로 판정한다. '
        '주어지지 않은 수치는 절대 지어내지 말고, 모든 근거 문장은 제공된 숫자를 인용한다. '
        '응답은 아래 스키마의 JSON 하나만 출력한다(설명/markdown 금지): '
        '{"label": str, "summary": str(<=120자), '
        '"rationale": [str,...](3~5개, 각 문장에 수치 인용), '
        '"news_keywords": [str,...](4~6개 테마/이벤트 키워드)}'
    )
    user = json.dumps(payload, ensure_ascii=False)
    parsed, provider, _errors = _call_llm(system, user)
    if not isinstance(parsed, dict):
        return None

    label = str(parsed.get('label') or '').strip() or rule_regime['label']
    summary = str(parsed.get('summary') or '').strip() or rule_regime['summary']
    rationale = [str(x).strip() for x in (parsed.get('rationale') or []) if str(x).strip()]
    news_kw = [str(x).strip() for x in (parsed.get('news_keywords') or []) if str(x).strip()]
    if not rationale:
        return None

    return {
        'label': label,
        'summary': summary,
        'rationale': rationale[:5],
        # 데이터 근거(숫자)는 규칙 결과를 그대로 유지해 검증 가능성을 보장
        'data_basis': rule_regime['data_basis'],
        'macro_points': rule_regime['macro_points'],
        'news_keywords': news_kw[:6] or None,
        'inputs': rule_regime['inputs'],
        'tilt': rule_regime['tilt'],
        'selective': rule_regime['selective'],
        'source': f'llm:{provider}' if provider else 'llm',
    }


def _build_market_regime(themes: List[Dict[str, Any]], keywords: str, use_llm: bool,
                         macro_snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    # 스냅샷을 명시 주입한 경우(테스트/외부 입력)는 캐시를 우회해 항상 그 입력으로 판정한다.
    use_cache = macro_snapshot is None
    cache_key = f'{keywords}|{use_llm}|{_iso_now()[:13]}'  # 시간대(시) 단위 캐시
    if use_cache:
        cached = _REGIME_CACHE.get(cache_key)
        if cached and (time.time() - cached[0]) < _REGIME_TTL_SEC:
            return cached[1]

    theme_scores = [t['score'] for t in themes] or [0]
    theme_spread = int(max(theme_scores) - min(theme_scores))
    snap = macro_snapshot if macro_snapshot is not None else _live_macro_snapshot()

    regime = _regime_from_rules(snap, theme_spread)
    if use_llm:
        llm_regime = _regime_with_llm(regime, themes)
        if llm_regime is not None:
            regime = llm_regime

    # 기존 프론트 호환: news_keywords 가 비면 상위 테마 태그로 채운다.
    if not regime.get('news_keywords'):
        tags: List[str] = []
        for t in themes[:5]:
            tags.extend(t.get('macro_tags', []))
        regime['news_keywords'] = list(dict.fromkeys(tags))[:6] or [
            'AI 인프라', '전력망', '방산 수출', '조선 수주', '밸류업']

    if use_cache:
        _REGIME_CACHE[cache_key] = (time.time(), regime)
    return regime


def _build_live_factor_maps(themes_src: List[Dict[str, Any]], regime_tilt: str
                            ) -> Tuple[Dict[str, Dict[str, int]], Dict[str, Dict[str, str]]]:
    """모든 테마 종목의 실데이터 팩터를 병렬 수집. 반환: (live_map, sources_map) by symbol."""
    from concurrent.futures import ThreadPoolExecutor

    items = [item for theme in themes_src for item in theme['symbols']]
    live_map: Dict[str, Dict[str, int]] = {}
    sources_map: Dict[str, Dict[str, str]] = {}

    def _one(item: Dict[str, Any]):
        try:
            return str(item['symbol']), _live_factor_scores(item, regime_tilt)
        except Exception:
            return str(item['symbol']), (None, None)

    with ThreadPoolExecutor(max_workers=6) as ex:
        for sym, (scores, sources) in ex.map(_one, items):
            if scores:
                live_map[sym] = scores
            if sources:
                sources_map[sym] = sources
    return live_map, sources_map


def _enrich_top_picks(top_picks: List[Dict[str, Any]], horizon_months: int) -> List[Dict[str, Any]]:
    """idea_engine.build_idea 로 top 5 픽의 thesis/why_now/evidence 를 실데이터 기반으로 보강.

    - 5개 픽을 ThreadPoolExecutor(max_workers=5)로 병렬 호출.
    - 각 픽의 enrichment 실패 시 template 결과 유지(graceful fallback).
    - evidence 는 build_idea 반환값({claim,source,value}) 을 factor 키가 있는 template 포맷으로
      변환해 덮어쓴다. 변환 후에도 ≥4개 & ≥4 distinct factor 조건을 만족하도록 보강한다.
    - evidence_source: 'idea_engine' 또는 'template' 태그 추가.
    """
    try:
        from . import idea_engine as ie
    except Exception:
        for p in top_picks:
            p['evidence_source'] = 'template'
        return top_picks

    horizon_str = f'{horizon_months}개월'

    def _enrich_one(pick: Dict[str, Any]) -> Dict[str, Any]:
        out = dict(pick)
        try:
            result = ie.build_idea(str(pick['symbol']), horizon=horizon_str)
            if not result or not isinstance(result, dict):
                raise ValueError('empty result')

            # thesis 보강 (비어있지 않은 경우만)
            new_thesis = str(result.get('thesis') or '').strip()
            if new_thesis and new_thesis != '투자 논거 미생성' and '종목을 식별하지 못했' not in new_thesis:
                out['thesis'] = new_thesis

            # why_now: key_drivers 가 있으면 이어붙여 서술
            drivers = [str(d).strip() for d in (result.get('key_drivers') or []) if str(d).strip()]
            if drivers:
                out['why_now'] = ' '.join(drivers[:3])

            # evidence: build_idea 의 {claim,source,value} 목록을 factor 포맷으로 변환,
            # 이후 원래 template evidence 와 병합해 factor 다양성 ≥ 4 보장
            raw_ev = [e for e in (result.get('evidence') or []) if isinstance(e, dict)]
            if raw_ev:
                # build_idea evidence 를 factor=None 으로 태깅해 앞에 추가
                engine_ev: List[Dict[str, Any]] = []
                for ev in raw_ev[:6]:
                    engine_ev.append({
                        'factor': None,          # factor 없음 → 프론트에서 generic 표시
                        'title': str(ev.get('claim') or '').strip(),
                        'detail': f"{ev.get('source','')} — {ev.get('value','')}".strip(' —'),
                        'source': str(ev.get('source') or ''),
                        'value': ev.get('value'),
                    })
                # template evidence 는 factor 가 있어 distinct-factor 조건을 충족시킨다 → 병합
                template_ev = list(pick.get('evidence') or [])
                merged = engine_ev + template_ev
                out['evidence'] = merged
            out['evidence_source'] = 'idea_engine'
        except Exception:
            out['evidence_source'] = 'template'
        return out

    enriched: List[Dict[str, Any]] = list(top_picks)
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(_enrich_one, p): i for i, p in enumerate(top_picks)}
        for fut, idx in futures.items():
            try:
                enriched[idx] = fut.result()
            except Exception:
                enriched[idx]['evidence_source'] = 'template'
    return enriched


def build_radar(keywords: str = '', horizon_months: int = 3, use_llm: bool = True,
                macro_snapshot: Optional[Dict[str, Any]] = None,
                use_live_factors: Optional[bool] = None,
                enrich_top_picks: Optional[bool] = None) -> Dict[str, Any]:
    # use_live_factors 미지정 시 use_llm 을 따른다 → 기존 테스트(use_llm=false)는 시드/결정론 유지(빠름)
    if use_live_factors is None:
        use_live_factors = use_llm
    # enrich_top_picks 미지정 시 use_llm 을 따른다(LLM 없이는 enrichment 비활성 → 테스트 결정론 유지)
    if enrich_top_picks is None:
        enrich_top_picks = use_llm

    themes_src = _select_themes(keywords)

    # 실데이터 팩터: regime tilt 를 먼저 산출(저비용) 후 종목 팩터를 병렬 수집
    live_map: Dict[str, Dict[str, int]] = {}
    sources_map: Dict[str, Dict[str, str]] = {}
    if use_live_factors:
        try:
            snap = macro_snapshot if macro_snapshot is not None else _live_macro_snapshot()
            tilt = _regime_from_rules(snap, 0).get('tilt', 'neutral')
        except Exception:
            tilt = 'neutral'
        try:
            live_map, sources_map = _build_live_factor_maps(themes_src, tilt)
        except Exception:
            live_map, sources_map = {}, {}
    used_live = bool(live_map)

    picks = [_pick(theme, item, live_map, sources_map) for theme in themes_src for item in theme['symbols']]
    picks.sort(key=lambda p: (p['conviction_score'] >= 65, p['score']), reverse=True)
    top_picks = picks[:5]

    # TASK A: enrich_top_picks=True 일 때만 실데이터 기반 thesis/evidence 보강
    if enrich_top_picks:
        top_picks = _enrich_top_picks(top_picks, horizon_months)
    else:
        for p in top_picks:
            p['evidence_source'] = 'template'

    # 타이밍 신호 (best-effort, 실패 시 enter 폴백)
    if use_live_factors:
        try:
            timing_map = _build_timing_map(top_picks)
            for p in top_picks:
                p['timing_signal'] = timing_map.get(str(p['symbol']), {'signal': 'enter'})
        except Exception:
            for p in top_picks:
                p.setdefault('timing_signal', {'signal': 'enter'})
    else:
        for p in top_picks:
            p.setdefault('timing_signal', {'signal': 'enter'})

    themes = []
    for theme in themes_src:
        theme_picks = [_pick(theme, item, live_map, sources_map) for item in theme['symbols']]
        best = max(theme_picks, key=lambda p: p['score'])
        avg = _clamp(sum(p['score'] for p in theme_picks) / len(theme_picks))
        themes.append({
            'theme': theme['theme'],
            'sector': theme['sector'],
            'score': avg,
            'macro_tags': theme['macro_tags'],
            'representatives': [{'symbol': p['symbol'], 'name': p['name'], 'score': p['score']} for p in theme_picks],
            'top_factors': sorted(best['factor_scores'].items(), key=lambda kv: kv[1], reverse=True)[:3],
            'commentary': f"{theme['theme']}은(는) 차트·뉴스·매크로가 함께 움직이는지 확인할 가치가 있습니다.",
        })
    themes.sort(key=lambda t: t['score'], reverse=True)
    market_regime = _build_market_regime(themes, keywords, use_llm, macro_snapshot)

    # VKOSPI를 market_regime에 추가 (best-effort)
    try:
        from .price_service import get_index
        vkospi_data = get_index('VKOSPI')
        if vkospi_data and vkospi_data.get('price') is not None:
            market_regime['vkospi'] = round(float(vkospi_data['price']), 1)
    except Exception:
        pass

    # 섹터 랭킹 (best-effort)
    sector_rank: List[Dict[str, Any]] = []
    if use_live_factors:
        try:
            sector_rank = _build_sector_rank()
        except Exception:
            pass

    newsflow = _build_newsflow_pipeline(market_regime, themes, top_picks, sector_rank)
    committee_minutes = _build_committee_minutes(market_regime, newsflow)

    return {
        'generated_at': _iso_now(),
        'horizon_months': int(horizon_months or 3),
        'keywords': keywords,
        'factor_weights': FACTOR_WEIGHTS,
        'market_regime': market_regime,
        'themes': themes,
        'top_picks': top_picks,
        'sector_rank': sector_rank,
        'pipeline': newsflow,
        'macro_flow': newsflow['macro'],
        'sector_flow': newsflow['sectors'],
        'stock_candidates': newsflow['stock_candidates'],
        'news_flow': newsflow['news_flow'],
        'committee_minutes': committee_minutes,
        'engine': 'newsflow_topdown',
        'data_quality': {
            'mode': 'live_factors' if used_live else 'deterministic_fallback',
            'regime_source': market_regime.get('source'),
            'warnings': [
                ('테마/종목 팩터는 실시간 데이터(pykrx OHLCV·수급·펀더멘털, 뉴스 RSS)로 산출하며, '
                 '개별 팩터 수집 실패 시 결정론 시드로 graceful degrade 합니다.')
                if used_live else
                '테마/종목 컴포짓 점수는 결정론 시드 기반입니다(실시간 공급자 실패 시에도 데모/테스트 가능).',
                'Market Regime 은 실시간 매크로(VIX·USD/KRW·지수)와 테마 점수 분산으로 판정하고, LLM 가용 시 서술을 보강합니다.',
                'RS 단독 랭킹이 아니라 6개 팩터를 함께 사용합니다.',
            ],
        },
    }


def _read_history() -> List[Dict[str, Any]]:
    try:
        if not HISTORY_PATH.exists():
            return []
        data = json.loads(HISTORY_PATH.read_text(encoding='utf-8'))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _write_history(items: Iterable[Dict[str, Any]]) -> None:
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    HISTORY_PATH.write_text(json.dumps(list(items), ensure_ascii=False, indent=2), encoding='utf-8')


def list_history() -> List[Dict[str, Any]]:
    return sorted(_read_history(), key=lambda x: x.get('created_at', ''), reverse=True)


def _fetch_price(symbol: Optional[str]) -> Optional[float]:
    """price_service.get_quote 로 현재가를 가져온다. 실패/미지정 시 None."""
    if not symbol:
        return None
    try:
        from .price_service import get_quote
        q = get_quote(str(symbol))
        p = q.get('price') if q else None
        if p is not None:
            return float(p)
    except Exception:
        pass
    return None


def save_history(pick: Dict[str, Any], note: str = '') -> Dict[str, Any]:
    today = _today()
    horizon_months = int(pick.get('horizon_months') or 3)

    # TASK B: 저장 시점의 현재가를 start_price 로 기록 (성과 추적 기준점)
    symbol = pick.get('symbol')
    start_price = _fetch_price(symbol)

    item = {
        'idea_id': f"{pick.get('symbol', 'UNKNOWN')}-{today.isoformat()}-{len(_read_history()) + 1}",
        'created_at': _iso_now(),
        'horizon_months': horizon_months,
        'horizon_end': (today + dt.timedelta(days=30 * horizon_months)).isoformat(),
        'status': 'new',
        'note': note,
        'symbol': symbol,
        'name': pick.get('name'),
        'theme': pick.get('theme'),
        'score': pick.get('score'),
        'thesis': pick.get('thesis'),
        'why_now': pick.get('why_now'),
        'factor_scores': pick.get('factor_scores', {}),
        'counter_evidence': pick.get('counter_evidence', []),
        'checklist': pick.get('checklist', []),
        'start_price': start_price,
        'start_date': today.isoformat(),
        'latest_price': None,
        'tracking_return': None,
        'thesis_watch': 'active',
    }
    items = _read_history()
    items.append(item)
    _write_history(items)
    return item


def list_history_with_performance() -> List[Dict[str, Any]]:
    """히스토리 목록에 현재가·추적수익률을 실시간 보강해 반환.

    - start_price 가 있는 활성 아이디어에 대해 현재가를 병렬 조회.
    - tracking_return_pct = (current - start) / start * 100
    - horizon_end < today 면 반환 뷰에서 status='expired' 로 표시(파일 미변경).
    - 가격 조회 실패 시 해당 아이디어는 tracking_return_pct=None, current_price=None.
    """
    items = list_history()
    today_iso = _today().isoformat()

    # start_price 가 있는 아이디어만 가격 조회 대상
    to_fetch = [(i, item) for i, item in enumerate(items)
                if item.get('start_price') is not None and item.get('symbol')]

    def _fetch_one(idx_item: Tuple[int, Dict[str, Any]]) -> Tuple[int, Optional[float]]:
        idx, item = idx_item
        try:
            return idx, _fetch_price(item['symbol'])
        except Exception:
            return idx, None

    price_map: Dict[int, Optional[float]] = {}
    if to_fetch:
        with ThreadPoolExecutor(max_workers=min(5, len(to_fetch))) as ex:
            for idx, price in ex.map(_fetch_one, to_fetch):
                price_map[idx] = price

    result = []
    for i, item in enumerate(items):
        out = dict(item)
        # horizon 만료 여부 (뷰 전용, 파일 미변경)
        horizon_end = str(out.get('horizon_end') or '')
        if horizon_end and horizon_end < today_iso and out.get('status') not in ('adopted', 'rejected'):
            out['status'] = 'expired'

        current_price = price_map.get(i)
        out['current_price'] = current_price
        start_price = out.get('start_price')
        if start_price and current_price is not None:
            try:
                out['tracking_return_pct'] = round((current_price - start_price) / start_price * 100, 2)
            except Exception:
                out['tracking_return_pct'] = None
        else:
            out['tracking_return_pct'] = None
        result.append(out)
    return result


def update_history(idea_id: str, status: Optional[str] = None, note: Optional[str] = None) -> Dict[str, Any]:
    items = _read_history()
    allowed = {'new', 'reviewing', 'watch', 'committee', 'adopted', 'rejected'}
    for item in items:
        if item.get('idea_id') == idea_id:
            if status:
                item['status'] = status if status in allowed else item.get('status', 'new')
            if note is not None:
                item['note'] = note
            item['updated_at'] = _iso_now()
            _write_history(items)
            return item
    raise KeyError(f'idea_id not found: {idea_id}')
