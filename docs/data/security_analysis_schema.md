# Security Analysis Dataset Schema

모든 파일 공통 필드:

- `source`: 원천. 예: ECOS, pykrx, OpenDART, Kiwoom, FMP_FREE, manual_seed.
- `as_of`: 데이터 기준 시각.
- `confidence`: 0~1 신뢰도. 무료/수동 seed는 낮게 시작한다.
- `license_tier`: `free`, `free_tier`, `free_seed`, `paid`, `internal`.

## 프로덕션 source policy

- 개별 종목 가격: `stock-server.snp_prices` 우선. MVP는 pykrx/FDR/marcap/Kiwoom.
- KOSPI/KOSDAQ: ECOS 전용.
- VIX: FMP `^VIX` 또는 무료 fallback. 반드시 caret prefix.
- 펀더멘털: FactSet FF_V3 우선. MVP는 OpenDART/OpenDartReader.
- 추정치: FactSet FE_V4 우선. MVP는 FMP free/manual consensus/broker parsed summary.
- 티커 해상: FactSet SYM_V1 우선. MVP는 FDR/pykrx/DART corp_code.

## 한국특화 GitHub adapter 후보

- `FinanceDataReader`: listing, price, index, FX.
- `OpenDartReader`: DART 재무/공시/지분.
- `marcap`: KRX 시가총액 장기 데이터.
- `pykrx`: 가격, 수급, 펀더멘털, 공매도, ETF.
- `cluefin`: Kiwoom/KIS/KRX/DART type-safe client pattern.
- `korea-stock-mcp`: DART/KRX 기반 AI 분석 MCP pattern.
- `kiwoom-rest-api`, `stockOpenAPI`, `Kiwoom_datareader`: Kiwoom 실시간/분봉/OCX 수집 reference.
