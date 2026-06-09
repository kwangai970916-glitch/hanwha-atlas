from __future__ import annotations

from app import price_service
from app.main import app
from fastapi.testclient import TestClient


def test_sector_returns_are_market_cap_weighted(monkeypatch):
    rows = [
        {"sector": "A", "change": 10.0, "market_cap": 90},
        {"sector": "A", "change": -10.0, "market_cap": 10},
        {"sector": "B", "change": 5.0, "market_cap": 100},
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: rows)

    sectors = price_service.get_sector_returns()
    by_name = {s["sector"]: s for s in sectors}

    assert by_name["A"]["change"] == 8.0
    assert by_name["A"]["count"] == 2
    assert by_name["B"]["change"] == 5.0


def test_snapshot_keeps_home_watchlist_compact(monkeypatch):
    full_rows = [
        {"symbol": f"{i:06d}", "display": f"S{i}", "price": 100, "change": 0.0, "asset_type": "stock", "sector": "A", "source": "test"}
        for i in range(30)
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: full_rows)
    monkeypatch.setattr(price_service, "get_index", lambda name: {"symbol": name, "display": name, "price": 1, "change_pct": 0, "change": 0, "source": "test"})
    monkeypatch.setattr(price_service, "get_quote", lambda code: {"symbol": code, "display": code, "price": 1, "change_pct": 0, "change": 0, "source": "test", "sector": "A"})
    price_service._cache.clear()

    ticks = price_service.get_ticks()["ticks"]
    stocks = [t for t in ticks if t.get("asset_type") == "stock"]

    assert len(stocks) == len(price_service.WATCH_STOCKS)
    assert len(ticks) < len(full_rows)


def test_universe_endpoint_searches_full_kospi(monkeypatch):
    rows = [
        {"symbol": "005930", "display": "????", "price": 100, "change": 1, "sector": "???", "market_cap": 1000},
        {"symbol": "000660", "display": "SK????", "price": 200, "change": 2, "sector": "???", "market_cap": 900},
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: rows)
    client = TestClient(app)

    body = client.get("/api/market/universe?q=005930").json()

    assert body["total"] == 1
    assert body["stocks"][0]["symbol"] == "005930"



def test_universe_calculates_kospi_contribution_points_and_sorts(monkeypatch):
    rows = [
        {"symbol": "000001", "display": "A", "price": 100, "change": 10.0, "sector": "Tech", "market_cap": 900},
        {"symbol": "000002", "display": "B", "price": 100, "change": -20.0, "sector": "Auto", "market_cap": 100},
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: rows)
    monkeypatch.setattr(price_service, "get_index", lambda name: {"price": 1010.0, "change": 10.0})

    body = price_service.get_kospi_universe(sort="contribution", order="desc", limit=10)

    assert body["total_market_cap"] == 1000
    assert body["stocks"][0]["symbol"] == "000001"
    assert body["stocks"][0]["raw_index_contribution_pt"] == 90.0
    assert body["stocks"][1]["raw_index_contribution_pt"] == -20.0
    assert round(sum(s["index_contribution_pt"] for s in body["stocks"]), 6) == 10.0


def test_universe_filters_by_sector_and_min_market_cap(monkeypatch):
    rows = [
        {"symbol": "000001", "display": "A", "price": 100, "change": 1.0, "sector": "Tech", "market_cap": 900},
        {"symbol": "000002", "display": "B", "price": 100, "change": 5.0, "sector": "Tech", "market_cap": 100},
        {"symbol": "000003", "display": "C", "price": 100, "change": 9.0, "sector": "Auto", "market_cap": 1000},
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: rows)
    monkeypatch.setattr(price_service, "get_index", lambda name: {"price": 1000.0, "change": 0.0})

    body = price_service.get_kospi_universe(sector="Tech", min_market_cap=500, sort="change", order="desc")

    assert body["total"] == 1
    assert body["stocks"][0]["symbol"] == "000001"



def test_normalized_contribution_points_sum_to_kospi_change(monkeypatch):
    rows = [
        {"symbol": "000001", "display": "A", "price": 100, "change": 10.0, "sector": "Tech", "market_cap": 900},
        {"symbol": "000002", "display": "B", "price": 100, "change": -20.0, "sector": "Auto", "market_cap": 100},
    ]
    monkeypatch.setattr(price_service, "_get_kospi_market_rows", lambda: rows)
    monkeypatch.setattr(price_service, "get_index", lambda name: {"price": 1010.0, "change": 10.0})

    enriched, meta = price_service._with_index_contribution(price_service._get_kospi_market_rows())

    assert round(sum(r["index_contribution_pt"] for r in enriched), 6) == 10.0
    assert meta["actual_index_change_pt"] == 10.0
    assert meta["normalization_factor"] != 1.0
