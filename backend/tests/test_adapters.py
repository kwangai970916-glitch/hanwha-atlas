import importlib
import sys
import types

import pandas as pd

from app.adapters.pykrx_adapter import PyKrxAdapter, normalize_ohlcv
from app.adapters.opendart_adapter import OpenDartReaderAdapter, normalize_finstate


def test_normalize_ohlcv_translates_korean_columns_and_index_date():
    raw = pd.DataFrame(
        {
            '시가': [1000],
            '고가': [1100],
            '저가': [900],
            '종가': [1050],
            '거래량': [12345],
        },
        index=pd.to_datetime(['2026-05-26']),
    )

    result = normalize_ohlcv(raw)

    assert result == [
        {
            'date': '2026-05-26',
            'open': 1000,
            'high': 1100,
            'low': 900,
            'close': 1050,
            'volume': 12345,
        }
    ]


def test_pykrx_adapter_reports_unavailable_when_package_missing(monkeypatch):
    original_import = importlib.import_module

    def fake_import(name):
        if name == 'pykrx.stock':
            raise ImportError('missing pykrx')
        return original_import(name)

    monkeypatch.setattr(importlib, 'import_module', fake_import)

    adapter = PyKrxAdapter()

    assert adapter.status()['available'] is False
    assert adapter.status()['reason'] == 'package_missing'


def test_pykrx_adapter_fetches_ohlcv_with_injected_pykrx_module(monkeypatch):
    fake_stock = types.SimpleNamespace(
        get_market_ohlcv_by_date=lambda start, end, ticker: pd.DataFrame(
            {'시가': [1], '고가': [2], '저가': [0], '종가': [1], '거래량': [10]},
            index=pd.to_datetime(['2026-05-26']),
        )
    )
    monkeypatch.setitem(sys.modules, 'pykrx.stock', fake_stock)

    adapter = PyKrxAdapter(stock_module=fake_stock)

    assert adapter.status()['available'] is True
    assert adapter.get_ohlcv('005930', '20260526', '20260526') == [
        {'date': '2026-05-26', 'open': 1, 'high': 2, 'low': 0, 'close': 1, 'volume': 10}
    ]


def test_normalize_finstate_keeps_common_open_dart_fields():
    raw = pd.DataFrame(
        [
            {
                'account_nm': '매출액',
                'fs_nm': '연결재무제표',
                'sj_nm': '손익계산서',
                'thstrm_amount': '1,234',
                'frmtrm_amount': '1,000',
            }
        ]
    )

    assert normalize_finstate(raw) == [
        {
            'account_name': '매출액',
            'financial_statement': '연결재무제표',
            'statement_name': '손익계산서',
            'current_amount': 1234,
            'previous_amount': 1000,
        }
    ]


def test_opendart_adapter_reports_unavailable_without_api_key(monkeypatch):
    monkeypatch.delenv('OPEN_DART_API_KEY', raising=False)

    adapter = OpenDartReaderAdapter()

    assert adapter.status()['available'] is False
    assert adapter.status()['reason'] == 'api_key_missing'


def test_opendart_adapter_reports_unavailable_when_package_missing(monkeypatch):
    monkeypatch.setenv('OPEN_DART_API_KEY', 'dummy-key')
    original_import = importlib.import_module

    def fake_import(name):
        if name == 'OpenDartReader':
            raise ImportError('missing OpenDartReader')
        return original_import(name)

    monkeypatch.setattr(importlib, 'import_module', fake_import)

    adapter = OpenDartReaderAdapter()

    assert adapter.status()['available'] is False
    assert adapter.status()['reason'] == 'package_missing'


def test_opendart_adapter_fetches_finstate_with_injected_reader():
    class FakeDart:
        def finstate(self, corp, year):
            return pd.DataFrame(
                [
                    {
                        'account_nm': '자산총계',
                        'fs_nm': '연결재무제표',
                        'sj_nm': '재무상태표',
                        'thstrm_amount': '2,500',
                        'frmtrm_amount': '2,000',
                    }
                ]
            )

    adapter = OpenDartReaderAdapter(api_key='dummy-key', reader=FakeDart())

    assert adapter.status()['available'] is True
    assert adapter.get_finstate('005930', 2025) == [
        {
            'account_name': '자산총계',
            'financial_statement': '연결재무제표',
            'statement_name': '재무상태표',
            'current_amount': 2500,
            'previous_amount': 2000,
        }
    ]
