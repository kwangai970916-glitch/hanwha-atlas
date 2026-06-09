from app import pnl


class FakeWb:
    def close(self):
        pass


def test_curve_context_uses_kospi_benchmark_even_when_reits_weight_is_larger(monkeypatch):
    holdings = [
        {"종목": "신한알파리츠", "주수": 10, "투자원금": 900.0},
        {"종목": "삼성전자", "주수": 1, "투자원금": 100.0},
    ]
    asset_rows = [
        {"internal_name": "신한알파리츠", "report_name": "신한알파리츠", "bm_name": "리츠TOP10"},
        {"internal_name": "삼성전자", "report_name": "삼성전자", "bm_name": "KOSPI"},
    ]
    dates = ["2026-05-27", "2026-05-28", "2026-05-29"]
    price_series = {
        pnl._normalize_name("신한알파리츠"): {"name": "신한알파리츠", "values": {dates[0]: 90.0, dates[1]: 91.0, dates[2]: 92.0}},
        pnl._normalize_name("삼성전자"): {"name": "삼성전자", "values": {dates[0]: 100.0, dates[1]: 101.0, dates[2]: 102.0}},
    }
    bm_series = {
        pnl._normalize_name("KOSPI"): {"name": "KOSPI", "values": {dates[0]: 100.0, dates[1]: 101.0, dates[2]: 102.0}},
        pnl._normalize_name("KRX 리츠 TOP10 지수"): {"name": "KRX 리츠 TOP10 지수", "values": {dates[0]: 100.0, dates[1]: 80.0, dates[2]: 70.0}},
    }

    monkeypatch.setattr(pnl, "_load_wb", lambda: FakeWb())
    monkeypatch.setattr(pnl, "_sheet_to_dicts", lambda wb, sheet: holdings if sheet == "현재보유" else asset_rows)
    monkeypatch.setattr(pnl, "_build_asset_master", lambda wb=None: {
        pnl._normalize_name("신한알파리츠"): {"report_name": "신한알파리츠", "bm_name": "리츠TOP10"},
        pnl._normalize_name("삼성전자"): {"report_name": "삼성전자", "bm_name": "KOSPI"},
    })
    monkeypatch.setattr(pnl, "_build_price_series", lambda: (dates, price_series))
    monkeypatch.setattr(pnl, "_build_bm_series", lambda: bm_series)
    monkeypatch.setattr(pnl, "_build_price_map", lambda: ({}, {}))
    monkeypatch.setattr(pnl, "_resolve_price", lambda name, price_map, asset_master: {"name": name})

    curve = pnl.get_pnl_curve("MAX")
    risk = pnl.get_pnl_risk("MAX")

    assert curve["bm_name"] == "KOSPI"
    assert risk["bm_name"] == "KOSPI"
    assert curve["bm_index"][-1] == 102.0


def test_bm_return_pct_uses_adjusted_bm_series_from_acquisition_to_latest():
    values = {
        "2026-05-27": 100.0,
        "2026-05-28": 103.0,
        "2026-05-29": 105.0,
    }
    assert pnl._bm_return_pct(values, "2026-05-28") == 1.94
