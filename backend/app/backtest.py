from __future__ import annotations

"""
백테스트 엔진 (기관급).

정합성 원칙
-----------
1) look-ahead 제거: 신호는 t시점까지의 데이터(과거~당일 종가)로 산출하고,
   체결은 t+1 시가에서 이뤄진다. 포지션 변화(체결) 이후의 수익은 t+1 종가부터
   반영되므로 동일봉 신호·체결 문제가 구조적으로 제거된다.
2) 거래비용: 포지션이 바뀐 날(체결일)에 한해
   매도세(0.18%, 매도 시) + 수수료(0.015%, 양방향) + 슬리피지(0.1%, 양방향)를
   해당일 수익률에서 차감한다.
3) 실벤치마크: BM = 자기자신 Buy&Hold가 아니라 KOSPI(1001) Buy&Hold 오버레이.
   (지수 조회 실패 시에만 자기자신 Buy&Hold로 graceful degrade하고 그 사실을 명시)
4) 다중 전략: ma_cross/sma, dual_momentum, bollinger, breakout52, vol_target.
5) 지표: CAGR/MDD/Sharpe/Sortino/Calmar/승률/회전율/연율변동성.
6) 산출물: equity_curve, trades(매매시점 마커), monthly(월별 수익률 히트맵용).
7) 고지(assumptions): 비용율, 생존편향 한계, 과거≠미래 명시.

순수 표준라이브러리 + pandas/pykrx만 사용. (새 패키지 금지)
python 3.9 호환.
"""

import datetime as dt
import math

# ---------------------------------------------------------------------------
# 비용 가정 (단위: 비율)
# ---------------------------------------------------------------------------
SELL_TAX = 0.0018        # 매도세 0.18% (매도 체결 시에만)
COMMISSION = 0.00015     # 수수료 0.015% (매수·매도 양방향)
SLIPPAGE = 0.001         # 슬리피지 0.1% (체결 양방향)

TRADING_DAYS = 252

# 전략 ID 표준화: 별칭 → 표준명
_STRATEGY_ALIASES = {
    "sma": "ma_cross",
    "ma": "ma_cross",
    "ma_cross": "ma_cross",
    "momentum": "dual_momentum",
    "dual_momentum": "dual_momentum",
    "dual": "dual_momentum",
    "bollinger": "bollinger",
    "bb": "bollinger",
    "breakout": "breakout52",
    "breakout52": "breakout52",
    "52w": "breakout52",
    "vol_target": "vol_target",
    "volatility": "vol_target",
    "voltarget": "vol_target",
}

_KNOWN_STRATEGIES = {"ma_cross", "dual_momentum", "bollinger", "breakout52", "vol_target"}


def _looks_like_date(s) -> bool:
    """문자열이 날짜(YYYY-MM-DD / YYYYMMDD)처럼 보이는지 판정."""
    if not isinstance(s, str):
        return False
    t = s.replace("-", "").replace("/", "").replace(".", "")
    return t.isdigit() and len(t) in (6, 8)


def _normalize_args(code, start, end, strategy):
    """
    유연한 시그니처 처리.

    지원 호출형태:
      run_backtest("005930")                       # 기본 전략·기본 기간
      run_backtest("005930", "sma")                # 2번째 인자가 전략명
      run_backtest("005930", "2024-01-01", "2025-01-01", "ma_cross")  # 구버전 위치인자
      run_backtest("005930", strategy="bollinger")
      run_backtest("005930", start="2020-01-01", end="2024-01-01", strategy="sma")
    """
    # 케이스: 2번째 위치 인자(start)가 사실은 전략명인 경우 (예: run_backtest(code, "sma"))
    if start is not None and not _looks_like_date(start) and end is None:
        # start 자리에 전략명이 들어온 것으로 간주
        if isinstance(start, str) and start.lower() in _STRATEGY_ALIASES:
            strategy = start
            start = None

    today = dt.date.today()
    if not end:
        end = today.isoformat()
    if not start:
        # 기본: 약 4년 lookback (모멘텀/52주 등 장기 지표 워밍업 확보)
        try:
            end_d = dt.date.fromisoformat(str(end)[:10].replace("/", "-"))
        except Exception:
            end_d = today
        start = (end_d - dt.timedelta(days=365 * 4 + 30)).isoformat()

    strat_key = (strategy or "ma_cross").lower()
    strat = _STRATEGY_ALIASES.get(strat_key, strat_key)
    if strat not in _KNOWN_STRATEGIES:
        strat = "ma_cross"
    return code, start, end, strat


# ---------------------------------------------------------------------------
# 전략 시그널 생성기
#   반환: target_position (0/1 또는 0~1 비중) — t시점까지의 데이터로만 산출.
#   look-ahead 방지를 위해 모든 시그널은 호출부에서 .shift(1) 처리한다.
# ---------------------------------------------------------------------------
def _signal_ma_cross(df, pd):
    closes = df["종가"].astype(float)
    ma5 = closes.rolling(5).mean()
    ma20 = closes.rolling(20).mean()
    return (ma5 > ma20).astype(float)


def _signal_dual_momentum(df, pd):
    """절대 모멘텀: 최근 120거래일(약 6개월) 수익률 > 0 이면 보유."""
    closes = df["종가"].astype(float)
    mom = closes.pct_change(120)
    return (mom > 0).astype(float)


def _signal_bollinger(df, pd):
    """
    볼린저밴드 평균회귀: 종가가 하단밴드 아래로 내려가면 매수(1),
    중심선(20MA) 위로 복귀하면 청산(0). 상태 유지형(state machine).
    """
    closes = df["종가"].astype(float)
    ma20 = closes.rolling(20).mean()
    std20 = closes.rolling(20).std()
    lower = ma20 - 2 * std20
    pos = []
    holding = 0
    for c, m, lo in zip(closes, ma20, lower):
        if pd.isna(m) or pd.isna(lo):
            pos.append(0.0)
            continue
        if holding == 0 and c < lo:
            holding = 1
        elif holding == 1 and c > m:
            holding = 0
        pos.append(float(holding))
    return pd.Series(pos, index=closes.index)


def _signal_breakout52(df, pd):
    """52주(약 252거래일) 신고가 돌파 추세추종. 종가가 직전 252일 최고가에 도달하면 보유,
    직전 126일(약 26주) 최저가로 떨어지면 청산. 상태 유지형."""
    closes = df["종가"].astype(float)
    hi = closes.rolling(252, min_periods=60).max()
    lo = closes.rolling(126, min_periods=30).min()
    pos = []
    holding = 0
    for c, h, l in zip(closes, hi, lo):
        if pd.isna(h) or pd.isna(l):
            pos.append(0.0)
            continue
        if holding == 0 and c >= h:
            holding = 1
        elif holding == 1 and c <= l:
            holding = 0
        pos.append(float(holding))
    return pd.Series(pos, index=closes.index)


def _signal_vol_target(df, pd, target_vol: float = 0.15):
    """
    변동성 타게팅: 연율 목표변동성(기본 15%)에 맞춰 비중을 0~1로 스케일.
    추세필터(20MA 상회 시에만 노출)와 결합. 비중 = clip(target/실현변동성, 0, 1).
    """
    closes = df["종가"].astype(float)
    ret = closes.pct_change()
    realized = ret.rolling(20).std() * math.sqrt(TRADING_DAYS)
    ma20 = closes.rolling(20).mean()
    weight = (target_vol / realized).clip(upper=1.0).fillna(0.0)
    trend = (closes > ma20).astype(float)
    w = (weight * trend).fillna(0.0)
    # 비중 변화 노이즈 축소: 0.05 단위로 양자화
    return (w * 20).round() / 20


_SIGNAL_FUNCS = {
    "ma_cross": _signal_ma_cross,
    "dual_momentum": _signal_dual_momentum,
    "bollinger": _signal_bollinger,
    "breakout52": _signal_breakout52,
    "vol_target": _signal_vol_target,
}

_STRATEGY_LABELS = {
    "ma_cross": "이동평균 교차(5/20)",
    "dual_momentum": "절대 모멘텀(120일)",
    "bollinger": "볼린저밴드 평균회귀(20,2σ)",
    "breakout52": "52주 신고가 돌파 추세추종",
    "vol_target": "변동성 타게팅(목표 15%)",
}


def _safe_div(a, b):
    return a / b if b not in (0, 0.0) else 0.0


def run_backtest(code: str, start: str = None, end: str = None,
                 strategy: str = "ma_cross") -> dict:
    """
    단일 종목 룰베이스 백테스트.

    Parameters
    ----------
    code : str   종목코드 (예: "005930")
    start, end : str  기간(YYYY-MM-DD). 생략 시 약 4년 lookback~오늘.
    strategy : str  전략 ID 또는 별칭
                    (sma|ma_cross, dual_momentum, bollinger, breakout52, vol_target)

    Returns
    -------
    dict  지표 + equity_curve + trades + monthly + assumptions + benchmark.
          실패 시 {"error": ...}
    """
    try:
        from pykrx import stock as krx
        import pandas as pd

        code, start, end, strat = _normalize_args(code, start, end, strategy)
        s_compact = start.replace("-", "")
        e_compact = end.replace("-", "")

        df = krx.get_market_ohlcv_by_date(s_compact, e_compact, code)
        if df is None or df.empty:
            return {"error": f"{code} 데이터 없음 (기간 {start}~{end})"}

        # 컬럼 안전 확보 (시가/종가)
        if "종가" not in df.columns:
            return {"error": f"{code} OHLCV 컬럼 비정상"}
        df = df[~df["종가"].isna()]
        if df.empty:
            return {"error": f"{code} 유효 종가 없음"}

        opens = df["시가"].astype(float) if "시가" in df.columns else df["종가"].astype(float)
        closes = df["종가"].astype(float)
        # 시가 0/결측 보정 (일부 종목 거래정지일)
        opens = opens.where(opens > 0, closes)
        dates = [str(d)[:10] for d in df.index]

        # --- 시그널 산출 (t시점까지의 정보) ---
        sig_func = _SIGNAL_FUNCS.get(strat, _signal_ma_cross)
        raw_signal = sig_func(df, pd).fillna(0.0)

        # --- look-ahead 제거: t에서 정해진 목표비중은 t+1 시가에 체결 ---
        # 즉, t+1 시가~t+1 종가, 그리고 그 이후 보유분에 수익 반영.
        # target[t] = raw_signal[t] (t 종가까지의 정보)
        # 실제 보유 포지션 position[t+1] 부터 적용.
        target = raw_signal.clip(lower=0.0, upper=1.0)
        # 체결은 다음 봉 시가 → 수익 인식은 다음 봉 시가 기준. 구현상:
        #   position_applied[i] = target[i-1]  (전일 신호가 당일에 비중으로 적용됨)
        position = target.shift(1).fillna(0.0)

        # 수익률: 보유 비중이 적용되는 동안의 일간 수익 (종가-종가 기준).
        # 체결 시점(비중이 바뀐 날)에는 시가 체결 가정 → 체결일 수익은
        # (종가/시가 - 1) * 신규비중 + 시가갭은 미보유로 간주(보수적).
        c2c_ret = closes.pct_change().fillna(0.0)         # 종가→종가 일간수익
        intraday_ret = (closes / opens - 1.0).fillna(0.0)  # 당일 시가→종가 수익

        prev_pos = position.shift(1).fillna(0.0)  # 전일 보유 비중
        # 체결 발생 여부 = 목표비중 변화. position[i] != prev_pos[i] 이면 i일 시가에 조정.
        turnover = (position - prev_pos).abs()

        # 일간 전략수익:
        #  - 체결이 없으면(비중 유지): c2c_ret * position
        #  - 체결이 있으면: 그 날은 시가에 비중 조정 → intraday_ret * position
        #    (시가 이전(전일종가→당일시가 갭)은 신규 비중에 미반영하여 보수적 처리)
        is_trade_day = turnover > 1e-9
        strat_ret = c2c_ret * position
        strat_ret = strat_ret.where(~is_trade_day, intraday_ret * position)

        # --- 거래비용 차감 (체결일에만) ---
        # 매수측 비용 = 증가분 * (수수료 + 슬리피지)
        # 매도측 비용 = 감소분 * (수수료 + 슬리피지 + 매도세)
        delta = position - prev_pos
        buy_amt = delta.clip(lower=0.0)
        sell_amt = (-delta).clip(lower=0.0)
        buy_cost = buy_amt * (COMMISSION + SLIPPAGE)
        sell_cost = sell_amt * (COMMISSION + SLIPPAGE + SELL_TAX)
        cost = (buy_cost + sell_cost).fillna(0.0)
        net_ret = strat_ret - cost

        cum = (1.0 + net_ret).cumprod()

        # --- 벤치마크: 실제 시장지수 Buy&Hold (자기자신 BM 금지) ---
        # 1순위: KOSPI 지수(1001). 2순위: KODEX 200 ETF(069500, KOSPI200 추종) 프록시
        #         — KRX 지수 OHLCV 엔드포인트가 불안정할 때를 위한 실시장 대체.
        # 3순위(최후): 종목 자기자신 Buy&Hold (그 사실을 명시·degrade 플래그).
        bm_source = None
        bm_degraded = False
        bm_cum = None
        bm_ret = None

        def _bm_from_close(close_series):
            cl = close_series.astype(float)
            cl = cl[cl > 0].reindex(df.index).ffill().bfill()
            r = cl.pct_change().fillna(0.0)
            return r, (1.0 + r).cumprod()

        # 1순위: KOSPI 지수
        try:
            idx = krx.get_index_ohlcv(s_compact, e_compact, "1001", name_display=False)
            if idx is not None and not idx.empty and "종가" in idx.columns and len(idx) > 1:
                bm_ret, bm_cum = _bm_from_close(idx["종가"])
                bm_source = "KOSPI(1001)"
        except Exception:
            bm_cum = None

        # 2순위: KODEX 200 ETF 프록시 (KOSPI200 추종)
        if bm_cum is None:
            try:
                etf = krx.get_market_ohlcv_by_date(s_compact, e_compact, "069500")
                if etf is not None and not etf.empty and "종가" in etf.columns and len(etf) > 1:
                    bm_ret, bm_cum = _bm_from_close(etf["종가"])
                    bm_source = "KOSPI200 (KODEX 200 ETF 069500 프록시)"
                    bm_degraded = True  # 지수 원본이 아닌 추종 ETF임을 표시
            except Exception:
                bm_cum = None

        # 3순위(최후): 종목 자기자신 Buy&Hold
        if bm_cum is None:
            bm_degraded = True
            bm_source = "종목 Buy&Hold (시장지수/ETF 조회 실패 폴백)"
            bm_ret = c2c_ret
            bm_cum = (1.0 + bm_ret).cumprod()

        # --- 지표 ---
        n = len(net_ret)
        years = max(n / TRADING_DAYS, 1e-9)
        final_mult = float(cum.iloc[-1])
        total_return = final_mult - 1.0
        cagr = final_mult ** (1.0 / years) - 1.0 if final_mult > 0 else -1.0

        roll_max = cum.cummax()
        drawdown = (cum - roll_max) / roll_max
        mdd = float(drawdown.min()) if n else 0.0

        ann_vol = float(net_ret.std() * math.sqrt(TRADING_DAYS)) if net_ret.std() > 0 else 0.0
        sharpe = _safe_div(float(net_ret.mean()) * TRADING_DAYS, ann_vol) if ann_vol > 0 else 0.0

        downside = net_ret[net_ret < 0]
        downside_dev = float(downside.std() * math.sqrt(TRADING_DAYS)) if len(downside) > 1 and downside.std() > 0 else 0.0
        sortino = _safe_div(cagr, downside_dev) if downside_dev > 0 else 0.0

        calmar = _safe_div(cagr, abs(mdd)) if mdd < 0 else 0.0

        # 승률: 보유(비중>0) 상태인 날의 수익 부호 기준
        held = net_ret[position > 0]
        win_rate = float((held > 0).mean()) if len(held) > 0 else 0.0

        # 회전율: 일평균 turnover의 연율화 (편도 기준 합 / 연수)
        annual_turnover = float(turnover.sum()) / years

        bm_final = float(bm_cum.iloc[-1])
        bm_total = bm_final - 1.0
        bm_cagr = bm_final ** (1.0 / years) - 1.0 if bm_final > 0 else -1.0

        # --- equity curve ---
        equity_curve = [
            {"date": d, "strategy": round(float(c), 4), "bm": round(float(b), 4)}
            for d, c, b in zip(dates, cum.tolist(), bm_cum.tolist())
        ]

        # --- trades (매매시점 마커) ---
        trades = []
        pos_list = position.tolist()
        prev_list = prev_pos.tolist()
        close_list = closes.tolist()
        open_list = opens.tolist()
        for i in range(n):
            d_chg = pos_list[i] - prev_list[i]
            if abs(d_chg) > 1e-9:
                side = "BUY" if d_chg > 0 else "SELL"
                trades.append({
                    "date": dates[i],
                    "side": side,
                    "price": round(float(open_list[i]), 2),   # t+1 시가 체결가
                    "weight_from": round(float(prev_list[i]), 3),
                    "weight_to": round(float(pos_list[i]), 3),
                    "equity": round(float(cum.iloc[i]), 4),
                })

        # --- 월별 수익률 (히트맵용) ---
        monthly = []
        try:
            net_series = pd.Series(net_ret.values, index=pd.to_datetime(df.index))
            m = (1.0 + net_series).resample("M").prod() - 1.0
            for ts, val in m.items():
                monthly.append({
                    "month": ts.strftime("%Y-%m"),
                    "year": int(ts.year),
                    "m": int(ts.month),
                    "return": round(float(val), 4),
                })
        except Exception:
            monthly = []

        return {
            "code": code,
            "strategy": strat,
            "strategy_label": _STRATEGY_LABELS.get(strat, strat),
            "period": {"start": dates[0], "end": dates[-1], "days": n},
            # 핵심 지표
            "total_return": round(total_return, 4),
            "cagr": round(cagr, 4),
            "mdd": round(mdd, 4),
            "sharpe": round(sharpe, 2),
            "sortino": round(sortino, 2),
            "calmar": round(calmar, 2),
            "win_rate": round(win_rate, 4),
            "annual_turnover": round(annual_turnover, 2),
            "annual_volatility": round(ann_vol, 4),
            # 벤치마크
            "benchmark": bm_source,
            "bm_return": round(bm_total, 4),
            "bm_cagr": round(bm_cagr, 4),
            "bm_degraded": bm_degraded,
            # 시계열/마커
            "equity_curve": equity_curve,
            "trades": trades,
            "monthly": monthly,
            # 사용 가능한 전략 목록 (프론트 셀렉터용)
            "available_strategies": [
                {"id": k, "label": _STRATEGY_LABELS[k]} for k in
                ["ma_cross", "dual_momentum", "bollinger", "breakout52", "vol_target"]
            ],
            # 고지
            "assumptions": {
                "sell_tax": SELL_TAX,
                "commission": COMMISSION,
                "slippage": SLIPPAGE,
                "fill_rule": "신호는 t시점까지 데이터로 산출, 체결은 t+1 시가(look-ahead 제거)",
                "cost_note": "매도세 0.18% + 수수료 0.015%(양방향) + 슬리피지 0.1%(양방향), 체결일에만 차감",
                "survivorship_bias": "상장폐지 종목 미포함 (생존편향 존재 — 결과 과대평가 가능)",
                "disclaimer": "과거 성과가 미래 수익을 보장하지 않음 (과거 != 미래)",
                "dividend_note": "배당 재투자 미반영 (가격수익률 기준)",
            },
        }
    except Exception as e:
        import traceback
        return {"error": str(e), "trace": traceback.format_exc()[-800:]}
