# -*- coding: utf-8 -*-
"""
손익현황(2번째 탭) 데모용 Mock 포트폴리오 — 단일 데이터셋 소스.

기존 엑셀 기반 pnl 로직은 그대로 보존하고, 이 모듈은 ATLAS_PNL_MOCK 플래그가
켜졌을 때만 pnl.py가 호출하는 '추가 레이어'다. 모든 PnL 엔드포인트
(summary / curve / risk / attribution / rolling-risk / trades)가 여기서 일관되게
파생되며, 핵심은 'BM = 포트폴리오 내 각 종목 BM의 비중 가중평균(합성 지수)'.

총 평가액 ≈ 2,000억. 국내 3 / 미국 3 / 중국 ETF 1.
시계열은 시드 고정으로 재현 가능(랜덤성 없음).
"""
from __future__ import annotations

import datetime as dt
import math
import random
from functools import lru_cache
from typing import Any

# ── 구성 상수 (쉽게 수정 가능) ──────────────────────────────────────────────
END_DATE = dt.date(2026, 6, 9)
N_DAYS = 252                 # ~1년치 거래일
SEED = 20260609
FX_USD = 1_352.5            # 달러/원 (mock)
BM_LABEL = "합성 BM (포트폴리오 가중)"
DEFAULT_RF = 0.03           # 무위험수익률(샤프용)

# 실제 수량×현재가로 평가액 산출 → 딱 떨어지지 않는 자연스러운 금액(총 ~1,980억).
# name, code, 지역, 통화, BM, 보유수량, 기간총수익률, BM대비베타, 현재가(자국통화)
HOLDINGS_DEF: list[dict[str, Any]] = [
    {"name": "삼성전자",           "code": "005930", "region": "국내", "ccy": "KRW", "bm": "KOSPI",     "qty": 581_300,  "ret":  0.163, "beta": 1.05, "px": 78_400.0},
    {"name": "SK하이닉스",         "code": "000660", "region": "국내", "ccy": "KRW", "bm": "KOSPI",     "qty": 167_400,  "ret":  0.387, "beta": 1.35, "px": 211_500.0},
    {"name": "한화에어로스페이스", "code": "012450", "region": "국내", "ccy": "KRW", "bm": "KOSPI",     "qty": 86_700,   "ret":  0.512, "beta": 1.20, "px": 341_000.0},
    {"name": "NVIDIA",             "code": "NVDA",   "region": "미국", "ccy": "USD", "bm": "NASDAQ100", "qty": 151_800,  "ret":  0.574, "beta": 1.40, "px": 141.20},
    {"name": "Apple",              "code": "AAPL",   "region": "미국", "ccy": "USD", "bm": "S&P500",    "qty": 94_600,   "ret":  0.096, "beta": 1.05, "px": 231.40},
    {"name": "Microsoft",          "code": "MSFT",   "region": "미국", "ccy": "USD", "bm": "S&P500",    "qty": 31_200,   "ret": -0.085, "beta": 1.00, "px": 468.90},
    {"name": "KODEX 차이나CSI300", "code": "283580", "region": "중국", "ccy": "KRW", "bm": "CSI300",    "qty": 742_000,  "ret": -0.062, "beta": 1.00, "px": 13_480.0},
]

# BM별 기간 총수익률·일변동성(mock)
BM_DEF: dict[str, dict[str, float]] = {
    "KOSPI":     {"ret": 0.15, "vol": 0.011},
    "S&P500":    {"ret": 0.14, "vol": 0.009},
    "NASDAQ100": {"ret": 0.22, "vol": 0.013},
    "CSI300":    {"ret": -0.02, "vol": 0.014},
}


# ── 시계열 유틸 ─────────────────────────────────────────────────────────────
def _trading_days(n: int, end: dt.date) -> list[str]:
    out: list[str] = []
    d = end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d -= dt.timedelta(days=1)
    return list(reversed(out))


def _log_steps(rng: random.Random, n: int, target_total: float, vol: float) -> list[float]:
    """n-1개의 일별 로그수익률(드리프트 보정으로 기간 총수익률=target_total 달성)."""
    raw = [rng.gauss(0.0, vol) for _ in range(n - 1)]
    drift = (math.log(1.0 + target_total) - sum(raw)) / (n - 1)
    return [x + drift for x in raw]


def _index_from_steps(steps: list[float]) -> list[float]:
    idx = [100.0]
    for s in steps:
        idx.append(idx[-1] * math.exp(s))
    return idx


def _std(xs: list[float]) -> float:
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def _cov(xs: list[float], ys: list[float]) -> float:
    n = min(len(xs), len(ys))
    if n < 2:
        return 0.0
    mx = sum(xs[:n]) / n
    my = sum(ys[:n]) / n
    return sum((xs[i] - mx) * (ys[i] - my) for i in range(n)) / (n - 1)


def _daily_rets(index: list[float]) -> list[float]:
    return [index[i] / index[i - 1] - 1.0 for i in range(1, len(index))]


def _mdd(index: list[float]) -> float:
    peak = -1e18
    mdd = 0.0
    for v in index:
        peak = max(peak, v)
        if peak > 0:
            mdd = min(mdd, v / peak - 1.0)
    return mdd


# ── 데이터셋 빌드(시드 고정 → 캐시) ────────────────────────────────────────
@lru_cache(maxsize=1)
def _dataset() -> dict[str, Any]:
    rng = random.Random(SEED)
    dates = _trading_days(N_DAYS, END_DATE)
    n = len(dates)

    # 1) BM 인덱스 시계열(로그스텝 공유 → 베타 상관 부여)
    bm_steps: dict[str, list[float]] = {}
    bm_index: dict[str, list[float]] = {}
    for name, d in BM_DEF.items():
        steps = _log_steps(rng, n, d["ret"], d["vol"])
        bm_steps[name] = steps
        bm_index[name] = _index_from_steps(steps)

    # 2) 종목별 인덱스 (= beta×BM + 고유노이즈, 기간수익률=목표)
    holdings: list[dict[str, Any]] = []
    holding_index: dict[str, list[float]] = {}
    for h in HOLDINGS_DEF:
        base = bm_steps[h["bm"]]
        idio = [rng.gauss(0.0, 0.006) for _ in range(n - 1)]
        raw = [h["beta"] * base[t] + idio[t] for t in range(n - 1)]
        drift = (math.log(1.0 + h["ret"]) - sum(raw)) / (n - 1)
        steps = [x + drift for x in raw]
        idx = _index_from_steps(steps)
        holding_index[h["name"]] = idx

        ret = idx[-1] / 100.0 - 1.0
        px_krw = h["px"] * (FX_USD if h["ccy"] == "USD" else 1.0)
        qty = h["qty"]
        value_krw = qty * px_krw
        cost_krw = value_krw / (1.0 + ret)
        unit_cost_native = h["px"] / (1.0 + ret)
        # 전일 대비(일간) — 마지막 스텝
        daily_r = math.exp(steps[-1]) - 1.0

        holdings.append({
            "name": h["name"], "code": h["code"], "region": h["region"],
            "ccy": h["ccy"], "bm": h["bm"], "weight": 0.0,  # 아래서 평가액 기준 산출
            "qty": qty,
            "price_native": round(h["px"], 2),
            "price": round(px_krw, 2),
            "unit_cost_native": round(unit_cost_native, 2),
            "value": round(value_krw, 0),
            "cost": round(cost_krw, 0),
            "pnl": round(value_krw - cost_krw, 0),
            "pnl_pct": round(ret * 100.0, 2),
            "daily_pnl": round(value_krw * daily_r, 0),
            "daily_pnl_pct": round(daily_r * 100.0, 2),
            "ret": ret,
        })

    # 2.5) 평가액 기준 비중 산출(현재가×수량)
    gross_value = sum(h["value"] for h in holdings)
    for h in holdings:
        h["weight"] = h["value"] / gross_value if gross_value else 0.0

    # 3) 포트폴리오 평가액 = Σ (종목 원가ᵢ × 종목지수ᵢ/100)  ← 금액가중(요약과 정합)
    total_cost = sum(h["cost"] for h in holdings)
    port_value = [sum(h["cost"] * holding_index[h["name"]][t] / 100.0 for h in holdings) for t in range(n)]
    port_index = [round(port_value[t] / total_cost * 100.0, 6) for t in range(n)]

    # 4) 합성 BM = Σ (종목 원가ᵢ × 종목 BMᵢ 지수/100), 원가가중 → 시작=100
    #    ← 핵심: 단순 KOSPI가 아니라 각 종목 BM의 포트폴리오 가중 합성 지수
    comp_bm_val = [sum(h["cost"] * bm_index[h["bm"]][t] / 100.0 for h in holdings) for t in range(n)]
    comp_bm = [round(comp_bm_val[t] / total_cost * 100.0, 6) for t in range(n)]

    # 5) 누적손익(평가액 - 원가). 종료 평가액 = Σ valueᵢ = 총 평가액.
    cum_pnl = [round(port_value[t] - total_cost, 0) for t in range(n)]
    total_value = port_value[-1]

    # BM 구성 비중(가중) — 표시용
    bm_weights: dict[str, float] = {}
    for h in holdings:
        bm_weights[h["bm"]] = bm_weights.get(h["bm"], 0.0) + h["weight"]

    return {
        "dates": dates, "n": n,
        "holdings": holdings,
        "holding_index": holding_index,
        "bm_index": bm_index,
        "port_index": port_index,
        "comp_bm": comp_bm,
        "port_value": port_value,
        "cum_pnl": cum_pnl,
        "total_cost": total_cost,
        "total_value": total_value,
        "bm_weights": bm_weights,
    }


def _slice_for_period(period: str | None) -> tuple[dict[str, Any], int]:
    ds = _dataset()
    keep = {"3M": 63, "1M": 21, "1Y": 252, "MAX": ds["n"]}.get(str(period or "MAX").upper(), ds["n"])
    k = min(keep, ds["n"])
    return ds, k


# ── 엔드포인트별 빌더 ──────────────────────────────────────────────────────
def mock_pnl_summary() -> dict[str, Any]:
    ds = _dataset()
    hs = ds["holdings"]
    total_value = sum(h["value"] for h in hs)
    total_cost = sum(h["cost"] for h in hs)
    total_pnl = total_value - total_cost
    total_daily = sum(h["daily_pnl"] for h in hs)
    holdings = []
    for h in hs:
        contrib = (h["pnl"] / total_pnl * 100.0) if total_pnl else 0.0
        holdings.append({
            "name": h["name"],
            "live_code": h["code"],
            "qty": h["qty"],
            "unit_cost": h["unit_cost_native"],
            "price": h["price_native"],
            "price_kind": "현재가",
            "price_currency": h["ccy"],
            "price_native": h["price_native"],
            "usd_converted": h["ccy"] == "USD",
            "value": h["value"],
            "pnl": h["pnl"],
            "pnl_pct": h["pnl_pct"],
            "daily_pnl": h["daily_pnl"],
            "daily_pnl_pct": h["daily_pnl_pct"],
            "ytd_pnl": h["pnl"],
            "ytd_pnl_pct": h["pnl_pct"],
            "live_price": h["price"],
            "live_currency": "KRW",
            "contribution_pct": round(contrib, 2),
            "region": h["region"],
            "bm_name": h["bm"],
        })
    return {
        "holdings": holdings,
        "total_cost": round(total_cost, 0),
        "total_value": round(total_value, 0),
        "total_pnl": round(total_pnl, 0),
        "total_pnl_pct": round(total_pnl / total_cost * 100.0, 2) if total_cost else 0,
        "total_daily_pnl": round(total_daily, 0),
        "total_daily_pnl_pct": round(total_daily / total_value * 100.0, 2) if total_value else 0,
        "realized_pnl_total": 1_820_000_000.0,
        "transactions": [],
        "as_of": END_DATE.isoformat(),
        "price_as_of": ds["dates"][-1],
        "live_price_as_of": ds["dates"][-1],
        "fetched_at": dt.datetime.now().isoformat(timespec="seconds"),
        "source": "mock",
        "summary": {
            "total_daily_pnl": round(total_daily, 0),
            "total_daily_pnl_pct": round(total_daily / total_value * 100.0, 2) if total_value else 0,
            "realized_pnl_total": 1_820_000_000.0,
        },
    }


def mock_pnl_curve(period: str | None = None) -> dict[str, Any]:
    ds, k = _slice_for_period(period)
    dates = ds["dates"][-k:]
    port_idx_full = ds["port_index"][-k:]
    comp_full = ds["comp_bm"][-k:]
    # 구간 시작=100 리베이스
    p0 = port_idx_full[0] or 100.0
    b0 = comp_full[0] or 100.0
    port_index = [round(v / p0 * 100.0, 4) for v in port_idx_full]
    bm_index = [round(v / b0 * 100.0, 4) for v in comp_full]
    total_cost = ds["total_cost"]
    port_value = [round(total_cost * v / 100.0, 0) for v in port_index]
    cum_pnl = [round(pv - total_cost, 0) for pv in port_value]
    realized = 1_820_000_000.0
    return {
        "dates": dates,
        "portfolio_value": port_value,
        "portfolio_index": port_index,
        "cum_pnl": cum_pnl,
        "portfolio_cost": round(total_cost, 0),
        "bm_index": bm_index,
        "bm_name": BM_LABEL,
        "bm_resolved": True,
        "coverage_pct": 100.0,
        "days": k,
        "period": str(period or "MAX").upper(),
        "as_of": dates[-1] if dates else None,
        "realized_cum": [round(realized, 0)] * len(dates),
        "total_incl_realized": [round(c + realized, 0) for c in cum_pnl],
        "realized_pnl_total": realized,
        "bm_components": [
            {"bm": b, "weight_pct": round(w * 100.0, 1)}
            for b, w in sorted(ds["bm_weights"].items(), key=lambda kv: -kv[1])
        ],
        "source": "mock",
    }


def mock_pnl_risk(period: str | None = None) -> dict[str, Any]:
    ds, k = _slice_for_period(period)
    port = ds["port_index"][-k:]
    bm = ds["comp_bm"][-k:]
    pr = _daily_rets(port)
    br = _daily_rets(bm)
    n = len(pr)
    ann = 252.0
    port_total = port[-1] / port[0] - 1.0
    bm_total = bm[-1] / bm[0] - 1.0
    years = n / ann if n else 1.0
    ann_return = (1.0 + port_total) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    bm_ann = (1.0 + bm_total) ** (1.0 / years) - 1.0 if years > 0 else 0.0
    ann_vol = _std(pr) * math.sqrt(ann)
    var_bm = _cov(br, br)
    beta = _cov(pr, br) / var_bm if var_bm else 0.0
    te = _std([pr[i] - br[i] for i in range(n)]) * math.sqrt(ann)
    excess = ann_return - bm_ann
    ir = excess / te if te else 0.0
    mdd = _mdd(port)
    sharpe = (ann_return - DEFAULT_RF) / ann_vol if ann_vol else None
    calmar = ann_return / abs(mdd) if mdd else None
    # 단위: ann_return/ann_vol/mdd/tracking_error/excess_return/bm_ann_return = 분수(소수)
    #       프론트가 ×100 하여 % 표시. beta/info_ratio/sharpe/calmar = 비율 원값.
    return {
        "ann_return": round(ann_return, 4),
        "ann_vol": round(ann_vol, 4),
        "mdd": round(mdd, 4),
        "beta": round(beta, 3),
        "tracking_error": round(te, 4),
        "info_ratio": round(ir, 3),
        "excess_return": round(excess, 4),
        "bm_ann_return": round(bm_ann, 4),
        "sharpe": round(sharpe, 3) if sharpe is not None else None,
        "calmar": round(calmar, 3) if calmar is not None else None,
        "bm_name": BM_LABEL,
        "bm_resolved": True,
        "coverage_pct": 100.0,
        "default_bm_used": False,
        "n_obs": n,
        "period": str(period or "MAX").upper(),
        "methodology": "포트폴리오 내 각 종목 BM을 비중 가중평균한 합성 BM 대비 산출",
        "source": "mock",
    }


def mock_pnl_attribution() -> dict[str, Any]:
    ds = _dataset()
    hs = ds["holdings"]
    total_value = sum(h["value"] for h in hs)
    total_pnl = sum(h["pnl"] for h in hs)
    groups_map: dict[str, dict[str, Any]] = {}
    for h in hs:
        g = groups_map.setdefault(h["region"], {"mv": 0.0, "pnl": 0.0, "cost": 0.0, "cnt": 0})
        g["mv"] += h["value"]
        g["pnl"] += h["pnl"]
        g["cost"] += h["cost"]
        g["cnt"] += 1
    order = {"국내": 0, "미국": 1, "중국": 2}
    groups = []
    for name, g in sorted(groups_map.items(), key=lambda kv: order.get(kv[0], 9)):
        groups.append({
            "group": name,
            "weight_pct": round(g["mv"] / total_value * 100.0, 2) if total_value else 0,
            "market_value": round(g["mv"], 0),
            "pnl": round(g["pnl"], 0),
            "pnl_contribution_pct": round(g["pnl"] / total_pnl * 100.0, 2) if total_pnl else 0,
            "avg_return_pct": round(g["pnl"] / g["cost"] * 100.0, 2) if g["cost"] else 0,
            "holdings_count": g["cnt"],
        })
    return {
        "groups": groups,
        "total_market_value": round(total_value, 0),
        "total_pnl": round(total_pnl, 0),
        "as_of": END_DATE.isoformat(),
        "source": "mock",
    }


def mock_pnl_rolling_risk(window: int = 60) -> dict[str, Any]:
    ds = _dataset()
    port = ds["port_index"]
    bm = ds["comp_bm"]
    dates = ds["dates"]
    pr = _daily_rets(port)
    br = _daily_rets(bm)
    rdates: list[str] = []
    betas: list[float | None] = []
    irs: list[float | None] = []
    w = max(20, int(window))
    for i in range(w, len(pr) + 1):
        seg_p = pr[i - w:i]
        seg_b = br[i - w:i]
        vb = _cov(seg_b, seg_b)
        beta = _cov(seg_p, seg_b) / vb if vb else 0.0
        diff = [seg_p[j] - seg_b[j] for j in range(w)]
        te = _std(diff) * math.sqrt(252)
        excess = (sum(seg_p) - sum(seg_b)) / w * 252
        ir = excess / te if te else 0.0
        rdates.append(dates[i])         # i번째 수익률 = dates[i]
        betas.append(round(beta, 3))
        irs.append(round(ir, 3))
    return {
        "dates": rdates,
        "beta": betas,
        "ir": irs,
        "window": w,
        "as_of": rdates[-1] if rdates else None,
        "bm_name": BM_LABEL,
        "source": "mock",
    }


def mock_pnl_trades(limit: int = 50, offset: int = 0, sort: str = "date", order: str = "desc") -> dict[str, Any]:
    # 실현 매도 내역(mock) — 누적 실현손익과 정합
    raw = [
        {"name": "POSCO홀딩스", "sell_date": "2026-02-12", "qty": "2,000",  "avg_buy_price": 410_000.0, "avg_sell_price": 455_000.0, "holding_days": 86,  "pnl": 90_000_000.0,  "return_pct": 10.98},
        {"name": "현대차",       "sell_date": "2026-03-05", "qty": "1,500",  "avg_buy_price": 245_000.0, "avg_sell_price": 268_000.0, "holding_days": 120, "pnl": 34_500_000.0,  "return_pct": 9.39},
        {"name": "TSLA",         "sell_date": "2026-03-21", "qty": "500",    "avg_buy_price": 250.0,     "avg_sell_price": 305.0,     "holding_days": 64,  "pnl": 37_125_000.0,  "return_pct": 22.0},
        {"name": "LG에너지솔루션","sell_date": "2026-04-09", "qty": "800",    "avg_buy_price": 380_000.0, "avg_sell_price": 352_000.0, "holding_days": 45,  "pnl": -22_400_000.0, "return_pct": -7.37},
        {"name": "네이버",       "sell_date": "2026-05-02", "qty": "1,200",  "avg_buy_price": 195_000.0, "avg_sell_price": 212_000.0, "holding_days": 150, "pnl": 20_400_000.0,  "return_pct": 8.72},
    ]
    reverse = str(order or "desc").lower() != "asc"
    key = str(sort or "date").lower()
    if key in ("pnl", "return_pct", "holding_days"):
        raw.sort(key=lambda t: t.get(key) or 0, reverse=reverse)
    else:
        raw.sort(key=lambda t: t["sell_date"], reverse=reverse)
    # 누적 실현손익
    cum = 0.0
    ordered_for_cum = sorted(raw, key=lambda t: t["sell_date"])
    cmap: dict[str, float] = {}
    for t in ordered_for_cum:
        cum += t["pnl"]
        cmap[t["sell_date"] + t["name"]] = cum
    for t in raw:
        t["cum_pnl"] = round(cmap[t["sell_date"] + t["name"]], 0)
    total = len(raw)
    page = raw[offset:offset + limit]
    return {
        "trades": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "sort": key,
        "order": "desc" if reverse else "asc",
        "source": "mock",
    }


# 보유종목 뉴스·공시 (mock) — code별 큐레이션
_HOLDING_NEWS: dict[str, list[dict[str, str]]] = {
    "005930": [
        {"time": "09:41", "title": "삼성전자, HBM4 양산 일정 앞당겨…엔비디아 공급 본격화 기대", "type": "news"},
        {"time": "08:55", "title": "[공시] 삼성전자 - 자기주식 취득 신탁계약 체결 결정", "type": "dart"},
    ],
    "000660": [
        {"time": "10:12", "title": "SK하이닉스, DDR5·HBM 수요 폭증에 주요 라인 가동률 풀가동", "type": "news"},
        {"time": "09:03", "title": "[공시] SK하이닉스 - 단일판매·공급계약 체결 (HBM 대형 고객)", "type": "dart"},
    ],
    "012450": [
        {"time": "09:58", "title": "한화에어로스페이스, 폴란드 K9 추가 물량 협상 막바지…유럽 방산 모멘텀", "type": "news"},
        {"time": "08:40", "title": "[공시] 한화에어로스페이스 - 신규 시설투자 등 결정", "type": "dart"},
    ],
    "NVDA": [
        {"time": "07:30", "title": "엔비디아, 차세대 Blackwell Ultra 수요 가이던스 상향…데이터센터 매출 사상 최대", "type": "news"},
        {"time": "07:05", "title": "엔비디아 CES 기조연설서 차세대 AI 가속기 로드맵 공개", "type": "news"},
    ],
    "AAPL": [
        {"time": "07:22", "title": "애플, AI 아이폰 교체 사이클 기대…서비스 매출 분기 최대치 경신", "type": "news"},
    ],
    "MSFT": [
        {"time": "07:18", "title": "마이크로소프트, Azure 성장 둔화·AI 설비투자 부담에 차익실현 매물", "type": "news"},
        {"time": "07:02", "title": "MS, 클라우드 가이던스 하향 우려…애널리스트 목표주가 일부 하향", "type": "news"},
    ],
    "283580": [
        {"time": "09:20", "title": "중국 본토 부양책 효과 제한…CSI300 약세, 외국인 순매도 지속", "type": "news"},
        {"time": "08:30", "title": "[공시] KODEX 차이나CSI300 - 분배금 지급 기준일 안내", "type": "dart"},
    ],
}


def mock_holdings_news(codes: str = "") -> dict[str, Any]:
    """보유종목 코드 기준 뉴스·공시(mock). 요청 코드만 필터링해 최신순 반환."""
    name_by_code = {h["code"]: h["name"] for h in HOLDINGS_DEF}
    req = [c.strip() for c in (codes or "").split(",") if c.strip()]
    if not req:
        req = list(_HOLDING_NEWS.keys())
    items: list[dict[str, str]] = []
    for code in req:
        for it in _HOLDING_NEWS.get(code, []):
            items.append({
                "time": it["time"],
                "name": name_by_code.get(code, code),
                "title": it["title"],
                "url": it.get("url", ""),
                "type": it["type"],
            })
    items.sort(key=lambda x: x["time"], reverse=True)
    return {"items": items[:24], "as_of": END_DATE.isoformat(), "source": "mock"}


def mock_holding_series(key: str, period: str | None = None) -> dict[str, Any]:
    """개별 종목 시계열(드로어용) — 종목 인덱스 vs 그 종목 BM."""
    ds, k = _slice_for_period(period)
    target = None
    for h in ds["holdings"]:
        if key and (key in h["name"] or h["name"] in key or key == h["code"]):
            target = h
            break
    if target is None:
        return {"name": key, "dates": [], "price_index": [], "bm_index": [],
                "bm_name": None, "period": str(period or "MAX").upper(), "as_of": None,
                "error": "종목 없음", "source": "mock"}
    dates = ds["dates"][-k:]
    hidx = ds["holding_index"][target["name"]][-k:]
    bidx = ds["bm_index"][target["bm"]][-k:]
    h0 = hidx[0] or 100.0
    b0 = bidx[0] or 100.0
    return {
        "name": target["name"],
        "dates": dates,
        "price_index": [round(v / h0 * 100.0, 4) for v in hidx],
        "bm_index": [round(v / b0 * 100.0, 4) for v in bidx],
        "bm_name": target["bm"],
        "period": str(period or "MAX").upper(),
        "as_of": dates[-1] if dates else None,
        "source": "mock",
    }
