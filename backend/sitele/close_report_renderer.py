# -*- coding: utf-8 -*-
"""Render a one-page domestic market close dashboard for Telegram."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from playwright.sync_api import sync_playwright


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _fmt_pct(value) -> str:
    value = _num(value)
    return f"{value:+.2f}%"


def _top(items, n=5, reverse=True):
    return sorted(items or [], key=lambda x: _num(x.get("change")), reverse=reverse)[:n]


def build_close_dashboard_data(report_data: dict | None = None) -> dict:
    """Normalize existing morning-report data into a close dashboard payload."""
    report_data = report_data or {}
    market = report_data.get("marketIndices") or {}
    kospi = market.get("kospi") or {}
    kosdaq = market.get("kosdaq") or {}
    sectors = report_data.get("sectorReturns") or []
    kosdaq_sectors = report_data.get("kosdaqSectors") or []
    gainers = report_data.get("topGainers") or []
    losers = report_data.get("topLosers") or []

    strong_sectors = _top(sectors + kosdaq_sectors, 5, reverse=True)
    weak_sectors = _top(sectors + kosdaq_sectors, 5, reverse=False)
    lead = strong_sectors[0]["sector"] if strong_sectors else "강세 업종"
    lag = weak_sectors[0]["sector"] if weak_sectors else "약세 업종"

    kospi_chg = _num(kospi.get("change"))
    kosdaq_chg = _num(kosdaq.get("change"))
    avg_chg = (kospi_chg + kosdaq_chg) / 2
    if avg_chg >= 0.4:
        badge = "RISK-ON"
        tone = "상승 우위"
    elif avg_chg <= -0.4:
        badge = "RISK-OFF"
        tone = "방어 우위"
    else:
        badge = "NEUTRAL"
        tone = "혼조"

    summary = [
        f"KOSPI {_fmt_pct(kospi_chg)}, KOSDAQ {_fmt_pct(kosdaq_chg)}로 {tone} 마감.",
        f"{lead} 강세, {lag} 약세로 업종별 차별화 진행.",
        "장마감 후 미국 선물·환율·외국인 선물 수급 확인 필요.",
    ]

    return {
        "date": report_data.get("date") or datetime.now().strftime("%Y.%m.%d"),
        "time": datetime.now().strftime("%H:%M"),
        "title": "금일장 요약 대시보드",
        "badge": badge,
        "kospi": {
            "name": "KOSPI",
            "index": _num(kospi.get("index")),
            "change": kospi_chg,
            "advance": int(kospi.get("advance") or report_data.get("kospiAdvance") or 0),
            "decline": int(kospi.get("decline") or report_data.get("kospiDecline") or 0),
            "unchanged": int(kospi.get("unchanged") or report_data.get("kospiUnchanged") or 0),
        },
        "kosdaq": {
            "name": "KOSDAQ",
            "index": _num(kosdaq.get("index")),
            "change": kosdaq_chg,
            "advance": int(kosdaq.get("advance") or report_data.get("kosdaqAdvance") or 0),
            "decline": int(kosdaq.get("decline") or report_data.get("kosdaqDecline") or 0),
            "unchanged": int(kosdaq.get("unchanged") or report_data.get("kosdaqUnchanged") or 0),
        },
        "summary": summary,
        "strongSectors": strong_sectors,
        "weakSectors": weak_sectors,
        "gainers": gainers[:5],
        "losers": losers[:5],
        "checkpoints": [
            "외국인 현·선물 수급 지속성",
            "반도체 대형주 종가 회복 여부",
            "원/달러 환율 1차 저항선 돌파 여부",
            "미국장 반도체·성장주 흐름",
        ],
    }


def render_close_dashboard(report_data: dict, output_path: str = "close_dashboard.png") -> str:
    """Render one PNG dashboard and return its path."""
    base_dir = Path(__file__).resolve().parent
    template_path = base_dir / "close_report_template.html"
    if not template_path.exists():
        raise FileNotFoundError(f"Template not found: {template_path}")

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    dashboard_data = build_close_dashboard_data(report_data)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 2048}, device_scale_factor=1)
        page.goto(template_path.as_uri())
        page.evaluate(f"window.reportData = {json.dumps(dashboard_data, ensure_ascii=False)}")
        page.evaluate("init()")
        page.wait_for_timeout(800)
        card = page.query_selector("#close-dashboard")
        if card is None:
            browser.close()
            raise RuntimeError("#close-dashboard element was not found")
        card.screenshot(path=str(output), type="png")
        browser.close()

    return os.fspath(output)
