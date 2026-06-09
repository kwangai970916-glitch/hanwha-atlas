from __future__ import annotations

from app import market_table


KR3 = "\uad6d\uace0\ucc44 3Y"
KR10 = "\uad6d\uace0\ucc44 10Y"
KR30 = "\uad6d\uace0\ucc44 30Y"


def test_market_table_bonds_include_korean_30y_and_bp_units(monkeypatch):
    def fake_kr_bond(name: str) -> dict:
        return {"close": {KR3: 3.1, KR10: 3.3, KR30: 3.2}[name], "chg_1d": 2.5}

    def fake_yf_bond_index(ticker: str) -> dict:
        return {"close": 4.25, "chg_1d": -1.0}

    def fake_yf(ticker: str, period: str = "5d") -> dict:
        return {"close": 100.0, "chg_1d": 0.5}

    monkeypatch.setattr(market_table, "_kr_bond", fake_kr_bond)
    monkeypatch.setattr(market_table, "_yf_bond_index", fake_yf_bond_index, raising=False)
    monkeypatch.setattr(market_table, "_yf", fake_yf)

    data = market_table.get_market_table()
    bond_names = [row["name"] for row in data["bonds"]]

    assert KR10 in bond_names
    assert KR30 in bond_names
    assert all(row["chg_unit"] == "bp" for row in data["bonds"])


def test_naver_bond_change_is_basis_points(monkeypatch):
    class Resp:
        encoding = "euc-kr"
        text = """
        <td class="date">2026.05.28</td><td class="num">3.25</td>
        <td class="date">2026.05.27</td><td class="num">3.20</td>
        """

    class Requests:
        @staticmethod
        def get(*args, **kwargs):
            return Resp()

    market_table._cache.clear()
    monkeypatch.setitem(__import__("sys").modules, "requests", Requests)

    out = market_table._naver_bond("IRR_GOVT03Y")

    assert out["close"] == 3.25
    assert out["chg_1d"] == 5.0
    assert out["chg_unit"] == "bp"



def test_kr_bond_uses_tradingeconomics_fallback_for_10y_30y(monkeypatch):
    def fake_pykrx(label: str) -> dict:
        return {}

    def fake_te(name: str) -> dict:
        return {"close": {KR10: 4.09, KR30: 4.034}[name], "chg_1d": {KR10: -6.0, KR30: -10.0}[name], "chg_unit": "bp"}

    monkeypatch.setattr(market_table, "_pykrx_bond", fake_pykrx)
    monkeypatch.setattr(market_table, "_tradingeconomics_bond", fake_te, raising=False)
    market_table._cache.clear()

    assert market_table._kr_bond(KR10) == {"close": 4.09, "chg_1d": -6.0, "chg_unit": "bp"}
    assert market_table._kr_bond(KR30) == {"close": 4.034, "chg_1d": -10.0, "chg_unit": "bp"}
