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
