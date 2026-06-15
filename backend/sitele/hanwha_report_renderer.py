# -*- coding: utf-8 -*-
"""
한화손보 운용본부 시황 리포트 — Playwright 렌더러
hanwha_report_template.html → PNG 스크린샷
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from playwright.sync_api import sync_playwright


# ── 슬롯 메타 ─────────────────────────────────────────────────────────────
SLOT_META = {
    "premarket": {"label": "장전 시황",   "time_default": "07:00"},
    "intraday":  {"label": "장중 시황",   "time_default": "08:30"},
    "close":     {"label": "장마감 시황", "time_default": "15:30"},
}

_SLOT_LABEL = {
    "premarket": "장전 시황",
    "close":     "장마감 시황",
    "intraday":  "장중 시황",
}


# ── 지수/수급/섹터/심리 데이터 패널 빌더 (공통) ──────────────────────────
def _build_data_panel(slot: str, market_data: dict[str, Any]) -> dict[str, Any]:
    indices: list[dict] = []

    if slot == "premarket":
        kr = market_data.get("kr_indices", {})
        kospi_prev = kr.get("kospi", {})
        if kospi_prev:
            indices.append({
                "name": "KOSPI (전일종가)",
                "value": float(kospi_prev.get("close", kospi_prev.get("index", 0))),
                "change": float(kospi_prev.get("chg_pct", kospi_prev.get("change", 0))),
                "highlight": True,
            })
        for name, info in market_data.get("us_indices", {}).items():
            indices.append({
                "name": name,
                "value": float(info.get("close", 0)),
                "change": float(info.get("change", 0)),
                "highlight": False,
            })
    else:
        kr = market_data.get("kr_indices", {})
        kospi = kr.get("kospi", {})
        kosdaq = kr.get("kosdaq", {})
        if kospi:
            indices.append({
                "name": "KOSPI",
                "value": float(kospi.get("close", kospi.get("index", 0))),
                "change": float(kospi.get("chg_pct", kospi.get("change", 0))),
                "highlight": True,
            })
        if kosdaq:
            indices.append({
                "name": "KOSDAQ",
                "value": float(kosdaq.get("close", kosdaq.get("index", 0))),
                "change": float(kosdaq.get("chg_pct", kosdaq.get("change", 0))),
                "highlight": True,
            })
        for name, info in market_data.get("us_indices", {}).items():
            indices.append({
                "name": name,
                "value": float(info.get("close", 0)),
                "change": float(info.get("change", 0)),
                "highlight": False,
            })

    inv_raw = market_data.get("investor", {})
    investor = {
        "available": bool(inv_raw and slot in ("intraday", "close")),
        "individual":  int(inv_raw.get("individual", 0)),
        "foreign":     int(inv_raw.get("foreign", 0)),
        "institution": int(inv_raw.get("institution", 0)),
    }

    sectors: list[dict] = (
        market_data.get("sectors")
        or market_data.get("sector_returns")
        or []
    )
    sectors = sorted(sectors, key=lambda x: float(x.get("change", 0)), reverse=True)[:12]

    sent_raw = market_data.get("sentiment", {})
    vix = sent_raw.get("vix")
    fg  = sent_raw.get("fear_greed")
    vix_label = (
        "안정" if vix and float(vix) < 15 else
        "경계" if vix and float(vix) < 20 else
        "위험" if vix and float(vix) < 25 else
        "공포" if vix else ""
    )
    fg_label = (
        "극도공포" if fg is not None and float(fg) <= 25 else
        "공포"     if fg is not None and float(fg) <= 45 else
        "중립"     if fg is not None and float(fg) <= 55 else
        "탐욕"     if fg is not None and float(fg) <= 75 else
        "극도탐욕" if fg is not None else ""
    )

    # breadth (advance / decline counts) — close slot only
    breadth_raw = market_data.get("breadth", {})
    breadth = {
        "up":   int(breadth_raw.get("up",   0)),
        "down": int(breadth_raw.get("down", 0)),
    }

    # macro rates panel (premarket)
    rates_raw = market_data.get("rates", {})
    rates = {
        "us10y":  rates_raw.get("us10y"),
        "dxy":    rates_raw.get("dxy"),
        "usdkrw": rates_raw.get("usdkrw"),
    }

    return {
        "indices":    indices,
        "investor":   investor,
        "sectors":    sectors,
        "breadth":    breadth,
        "rates":      rates,
        "top_movers": market_data.get("top_movers", {}),
        "sentiment": {
            "vix":              vix,
            "vix_label":        vix_label,
            "fear_greed":       fg,
            "fear_greed_label": fg_label,
            "usdkrw": sent_raw.get("usdkrw") or rates_raw.get("usdkrw"),
            "vkospi": sent_raw.get("vkospi"),
            "per":    sent_raw.get("per"),
            "pbr":    sent_raw.get("pbr"),
        },
        "index_chart": market_data.get("index_chart", {}),
    }


# ── 페이로드 빌더: envelope(신규) / legacy(구형) 모두 지원 ─────────────────
def build_report_payload(
    slot: str,
    sections: dict[str, Any],
    market_data: dict[str, Any],
) -> dict[str, Any]:
    """
    HTML 템플릿의 window.reportData에 주입할 딕셔너리 구성.

    sections가 새 envelope 포맷('blocks' 키 보유)이면 envelope 경로로,
    구형 9-key dict이면 legacy 경로로 처리(하위 호환).

    Parameters
    ----------
    slot        : 'premarket' | 'intraday' | 'close'
    sections    : generate_report_sections() 반환값 (envelope 또는 legacy dict)
    market_data : 슬롯별 원시 데이터
    """
    meta = SLOT_META.get(slot, {"label": "시황", "time_default": "—"})
    now = datetime.now()
    data_panel = _build_data_panel(slot, market_data)

    is_envelope = "blocks" in sections

    if is_envelope:
        # ── 신규 envelope 경로 ─────────────────────────────────────────────
        return {
            "mode":       "envelope",
            "slot":       slot,
            "slot_label": _SLOT_LABEL.get(slot, meta["label"]),
            "date":       now.strftime("%Y.%m.%d"),
            "time":       now.strftime("%H:%M"),
            "persona":    sections.get("persona", ""),
            "title":      sections.get("title", "—"),
            "stance":     sections.get("stance", "NEUTRAL"),
            "headline":   sections.get("headline", "—"),
            "blocks":     sections.get("blocks", []),
            "as_of":      sections.get("as_of", now.isoformat(timespec="seconds")),
            "data_panel": data_panel,
        }
    else:
        # ── 구형 legacy 경로 (하위 호환) ──────────────────────────────────
        return {
            "mode":       "legacy",
            "slot":       slot,
            "slot_label": meta["label"],
            "date":       now.strftime("%Y.%m.%d"),
            "time":       now.strftime("%H:%M"),
            "title":      sections.get("title", "—"),
            "stance":     sections.get("stance", "NEUTRAL"),
            "sections": {
                "key_issue": sections.get("key_issue", ""),
                "bull_case": sections.get("bull_case", ""),
                "bear_case": sections.get("bear_case", ""),
                "macro_flow": sections.get("macro_flow", ""),
                "kr_outlook": sections.get("kr_outlook", ""),
                "strategy":   sections.get("strategy", ""),
                "news_flow":  sections.get("news_flow", ""),
            },
            "data_panel": data_panel,
        }


# ── 렌더러 ────────────────────────────────────────────────────────────────
def render_hanwha_report(
    slot: str,
    sections: dict[str, Any],
    market_data: dict[str, Any],
    output_path: Optional[str] = None,
) -> str:
    """
    시황 리포트를 PNG로 렌더링하여 경로 반환.

    Parameters
    ----------
    slot         : 'premarket' | 'intraday' | 'close'
    sections     : generate_report_sections() 결과 (envelope 또는 legacy dict)
    market_data  : 슬롯별 원시 데이터
    output_path  : 출력 PNG 경로 (미지정 시 output/{yyyymmdd}/ 자동 생성)

    Returns
    -------
    str  저장된 PNG 파일의 절대 경로
    """
    base_dir = Path(__file__).resolve().parent
    if slot == "close":
        template = base_dir / "hanwha_close_template.html"
    else:
        template = base_dir / "hanwha_report_template.html"
    if not template.exists():
        raise FileNotFoundError(f"템플릿 없음: {template}")

    if output_path is None:
        date_str = datetime.now().strftime("%Y%m%d")
        out_dir = base_dir / "output" / date_str
        out_dir.mkdir(parents=True, exist_ok=True)
        fname = f"hanwha_{slot}_{datetime.now().strftime('%H%M')}.png"
        output_path = str(out_dir / fname)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    payload = build_report_payload(slot, sections, market_data)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1240, "height": 1754},
            device_scale_factor=1,
        )
        page.goto(template.as_uri())
        # 폰트 로딩 대기 (Pretendard / Noto Sans KR CDN)
        page.wait_for_timeout(2500)
        page.evaluate(
            f"window.reportData = {json.dumps(payload, ensure_ascii=False)}"
        )
        page.evaluate("init()")
        page.wait_for_timeout(600)

        el = page.query_selector("#hanwha-report")
        if el is None:
            browser.close()
            raise RuntimeError("#hanwha-report 요소를 찾을 수 없습니다")
        box = el.bounding_box()
        # 내용이 1160px를 초과해도 정확히 A4(820×1160)로 강제 클립
        page.screenshot(
            path=output_path,
            type="png",
            clip={"x": box["x"], "y": box["y"], "width": 820, "height": 1160},
        )
        browser.close()

    print(f"[렌더] PNG 저장 완료: {output_path}")
    return os.fspath(output_path)
