"""pykrx adapter and Korean OHLCV normalization helpers."""

from __future__ import annotations

import importlib
from typing import Any, Dict, List, Optional

import pandas as pd


_OHLCV_COLUMNS = {
    '시가': 'open',
    '고가': 'high',
    '저가': 'low',
    '종가': 'close',
    '거래량': 'volume',
    '거래대금': 'trading_value',
    '등락률': 'change_rate',
}


def _scalar(value: Any) -> Any:
    if pd.isna(value):
        return None
    if hasattr(value, 'item'):
        return value.item()
    return value


def normalize_ohlcv(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """Normalize pykrx Korean OHLCV rows to API-friendly dictionaries."""
    if frame is None or frame.empty:
        return []

    normalized = frame.rename(columns=_OHLCV_COLUMNS).copy()
    rows: List[Dict[str, Any]] = []
    for index, row in normalized.iterrows():
        item: Dict[str, Any] = {'date': pd.Timestamp(index).strftime('%Y-%m-%d')}
        for column in ['open', 'high', 'low', 'close', 'volume', 'trading_value', 'change_rate']:
            if column in normalized.columns:
                item[column] = _scalar(row[column])
        rows.append(item)
    return rows


class PyKrxAdapter:
    """Thin optional adapter around ``pykrx.stock``."""

    def __init__(self, stock_module: Optional[Any] = None) -> None:
        self._stock = stock_module
        self._unavailable_reason: Optional[str] = None
        if self._stock is None:
            try:
                self._stock = importlib.import_module('pykrx.stock')
            except ImportError:
                self._unavailable_reason = 'package_missing'

    def status(self) -> Dict[str, Any]:
        if self._unavailable_reason:
            return {'name': 'pykrx', 'available': False, 'reason': self._unavailable_reason}
        return {'name': 'pykrx', 'available': True, 'reason': None}

    def get_ohlcv(self, ticker: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
        if self._stock is None:
            return []
        frame = self._stock.get_market_ohlcv_by_date(start_date, end_date, ticker)
        return normalize_ohlcv(frame)
