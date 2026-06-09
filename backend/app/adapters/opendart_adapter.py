"""OpenDartReader adapter and financial statement normalization helpers."""

from __future__ import annotations

import importlib
import os
from typing import Any, Dict, List, Optional

import pandas as pd


_FINSTATE_COLUMNS = {
    'account_nm': 'account_name',
    'fs_nm': 'financial_statement',
    'sj_nm': 'statement_name',
    'thstrm_amount': 'current_amount',
    'frmtrm_amount': 'previous_amount',
}


def _amount(value: Any) -> Any:
    if pd.isna(value):
        return None
    if isinstance(value, str):
        stripped = value.replace(',', '').strip()
        if stripped in {'', '-'}:
            return None
        try:
            return int(stripped)
        except ValueError:
            try:
                return float(stripped)
            except ValueError:
                return value
    if hasattr(value, 'item'):
        return value.item()
    return value


def normalize_finstate(frame: pd.DataFrame) -> List[Dict[str, Any]]:
    """Normalize common OpenDartReader ``finstate`` columns."""
    if frame is None or frame.empty:
        return []

    normalized = frame.rename(columns=_FINSTATE_COLUMNS).copy()
    rows: List[Dict[str, Any]] = []
    for _, row in normalized.iterrows():
        item: Dict[str, Any] = {}
        for column in [
            'account_name',
            'financial_statement',
            'statement_name',
            'current_amount',
            'previous_amount',
        ]:
            if column in normalized.columns:
                value = row[column]
                item[column] = _amount(value) if column.endswith('_amount') else value
        rows.append(item)
    return rows


class OpenDartReaderAdapter:
    """Thin optional adapter around OpenDartReader."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        reader: Optional[Any] = None,
        env_var: str = 'OPEN_DART_API_KEY',
    ) -> None:
        self._api_key = api_key or os.getenv(env_var)
        self._reader = reader
        self._unavailable_reason: Optional[str] = None

        if self._reader is not None:
            return
        if not self._api_key:
            self._unavailable_reason = 'api_key_missing'
            return
        try:
            factory = importlib.import_module('OpenDartReader')
        except ImportError:
            self._unavailable_reason = 'package_missing'
            return
        constructor = getattr(factory, 'OpenDartReader', factory)
        self._reader = constructor(self._api_key)

    def status(self) -> Dict[str, Any]:
        if self._unavailable_reason:
            return {'name': 'OpenDartReader', 'available': False, 'reason': self._unavailable_reason}
        return {'name': 'OpenDartReader', 'available': True, 'reason': None}

    def get_finstate(self, corp: str, year: int) -> List[Dict[str, Any]]:
        if self._reader is None:
            return []
        frame = self._reader.finstate(corp, year)
        return normalize_finstate(frame)
