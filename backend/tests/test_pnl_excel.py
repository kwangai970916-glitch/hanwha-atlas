# backend/tests/test_pnl_excel.py
from app.pnl import _normalize_name, _build_price_map, get_pnl_summary


def test_normalize_strips_spaces_and_parens():
    assert _normalize_name("맥쿼리인프라(장기무)") == _normalize_name("맥쿼리인프라장기무")


def test_price_map_has_known_assets():
    pm, _meta = _build_price_map()
    # 엑셀 존재 시에만 검증 (CI에서 파일 없으면 skip)
    if not pm:
        return
    keys = " ".join(pm.keys())
    assert "신한알파리츠" in "".join(k for k in pm) or any("신한알파" in k for k in pm)


def test_pnl_summary_shape():
    d = get_pnl_summary()
    assert "holdings" in d and "total_value" in d
    if d.get("holdings"):
        h = d["holdings"][0]
        assert {"name", "qty", "price", "value", "pnl", "pnl_pct", "matched"} <= set(h)
