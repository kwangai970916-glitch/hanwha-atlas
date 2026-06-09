# backend/scripts/calibrate_price_raw.py
"""Price_Raw(인포) 컬럼 정렬을 KRX 코드(row1)로 검증한다. 1회용 진단 도구."""
from __future__ import annotations
import sys
from pathlib import Path

EXCEL = Path(__file__).resolve().parents[1] / "data" / "주간주식시황_V10_마스터파일.xlsx"


def main() -> None:
    import openpyxl
    wb = openpyxl.load_workbook(EXCEL, read_only=True, data_only=True)
    ws = wb["Price_Raw(인포)"]
    rows = list(ws.iter_rows(values_only=True))
    code_row = rows[0]          # KRX 코드(일부)
    name_row = rows[3]          # 자산명
    type_row = rows[4]          # 현재가/기준가
    # 마지막 데이터행
    last = next((r for r in reversed(rows) if r and r[0] is not None and any(v is not None for v in r[1:])), None)
    wb.close()

    ncol = max(len(name_row), len(last))
    print(f"{'col':>3} {'code':>8} {'name(c|c-1)':<28} {'type':<6} {'latest':>12}")
    for c in range(1, ncol):
        name = (name_row[c] if c < len(name_row) and name_row[c] else
                (name_row[c-1] if c-1 < len(name_row) else None))
        typ = type_row[c] if c < len(type_row) else None
        val = last[c] if c < len(last) else None
        code = code_row[c] if c < len(code_row) and code_row[c] else ""
        if name or val:
            print(f"{c:>3} {str(code):>8} {str(name):<28} {str(typ):<6} {str(val):>12}")


if __name__ == "__main__":
    main()
