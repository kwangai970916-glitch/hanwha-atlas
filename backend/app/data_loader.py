from __future__ import annotations

from pathlib import Path
import csv
import json
from functools import lru_cache

SAMPLE_DIR = Path(__file__).resolve().parents[2] / "data" / "samples"


@lru_cache(maxsize=1)
def load_market_summary() -> dict:
    return json.loads((SAMPLE_DIR / "market_summary.json").read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_sectors() -> list[dict]:
    return _read_csv("sector_snapshot.csv")


@lru_cache(maxsize=1)
def load_stocks() -> list[dict]:
    return _read_csv("stock_universe.csv")


@lru_cache(maxsize=1)
def load_news() -> list[dict]:
    return json.loads((SAMPLE_DIR / "news_headlines.json").read_text(encoding="utf-8-sig"))


@lru_cache(maxsize=1)
def load_dart_events() -> list[dict]:
    return json.loads((SAMPLE_DIR / "dart_events.json").read_text(encoding="utf-8-sig"))


def _read_csv(name: str) -> list[dict]:
    with (SAMPLE_DIR / name).open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))
