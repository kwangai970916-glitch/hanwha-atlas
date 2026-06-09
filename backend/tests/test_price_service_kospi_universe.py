from __future__ import annotations

import sys
import types

from app import price_service


class FakeLoc:
    def __init__(self, rows):
        self.rows = rows

    def __getitem__(self, code):
        return self.rows[code]


class FakeFrame:
    empty = False
    columns = ["Close", "Change", "ChangeAbs"]

    def __init__(self):
        self._rows = {
            "000001": {"Close": 1000, "Change": 1.5, "ChangeAbs": 15},
            "000002": {"Close": 2000, "Change": -0.5, "ChangeAbs": -10},
        }
        self.index = list(self._rows)
        self.loc = FakeLoc(self._rows)


class FakeKrx:
    @staticmethod
    def get_market_ticker_list(day, market="KOSPI"):
        return ["000001", "000002"] if market == "KOSPI" else []

    @staticmethod
    def get_market_ticker_name(code):
        return {"000001": "AAA", "000002": "BBB"}[code]

    @staticmethod
    def get_market_ohlcv_by_ticker(day, market="KOSPI"):
        return FakeFrame()

    @staticmethod
    def get_index_ticker_list(market="KOSPI"):
        return ["I001"]

    @staticmethod
    def get_index_ticker_name(index_code):
        return "Test Industry"

    @staticmethod
    def get_index_portfolio_deposit_file(index_code):
        return ["000001", "000002"]


def test_universe_rows_use_all_kospi_stocks_with_sector_mapping(monkeypatch):
    fake_pykrx = types.ModuleType("pykrx")
    fake_pykrx.stock = FakeKrx
    monkeypatch.setitem(sys.modules, "pykrx", fake_pykrx)
    monkeypatch.setitem(sys.modules, "pykrx.stock", FakeKrx)
    monkeypatch.setattr(price_service, "_naver_kospi_market_rows", lambda: [])
    monkeypatch.setattr(price_service, "_naver_upjong_sector_map", lambda: {})
    price_service._cache.clear()

    stocks = price_service._get_kospi_market_rows()

    assert {t["symbol"] for t in stocks} == {"000001", "000002"}
    assert {t["sector"] for t in stocks} == {"Test Industry"}
