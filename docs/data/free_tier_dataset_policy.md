# 데이터셋 구축 정책: 무료/한국특화 우선

## 1. 왜 이렇게 구성하는가

사용자가 제시한 프로덕션 운영 원칙은 유지한다. 다만 FactSet, S&P Capital IQ, LSEG, MT Newswires, StreetAccount 등은 라이선스 기반이므로 MVP에서는 직접 사용하지 않는다. 대신 같은 논리 계층을 무료/무료요금제/오픈소스 원천으로 대체한다.

핵심은 다음이다.

- 프로덕션 인터페이스명은 유지한다.
- MVP adapter만 무료 원천으로 구현한다.
- 모든 데이터는 `source`, `as_of`, `confidence`, `license_tier`를 가진다.
- LLM은 숫자를 생성하지 않는다.
- 증권분석 보고서는 데이터셋에서 계산된 결과만 사용한다.

## 2. 무료/오픈소스 우선순위

### 한국 주식

1. **pykrx**: KRX 가격, 투자자별 매매, 펀더멘털, 공매도, ETF 등 한국 시장 특화.
2. **FinanceDataReader**: KRX/KOSPI/KOSDAQ/KONEX listing, 가격, 지수, FX, ETF listing.
3. **FinanceData marcap**: 1995년 이후 KRX 일별 시가총액 데이터. size/liquidity/market-cap factor에 유용.
4. **OpenDartReader / OpenDART API**: 한국 공시, 재무제표, 지분공시, 주요사항보고.
5. **Kiwoom OpenAPI+/REST**: 실시간 quote, 체결, 분봉, 조건검색, 투자자 실무용 데이터. Windows/계좌/API 신청 제약 고려.
6. **ECOS**: KOSPI/KOSDAQ 및 한국 매크로 authoritative source.
7. **Naver News API/RSS**: 한국어 뉴스 이벤트 후보.

### 글로벌/미국

1. **FRED**: 미국 매크로.
2. **SEC EDGAR**: 미국 공시 원문.
3. **FMP free**: quote, financials, analyst target 일부. 무료 quota 제한을 캐시로 보완.
4. **yfinance**: 연구/교육용 fallback. 프로덕션 권위 source로 사용하지 않음.

## 3. 유료 벤더 대응 관계

| 프로덕션 권위 source | MVP 무료 대체 | 용도 |
|---|---|---|
| stock-server snp_prices | pykrx/FDR/marcap/Kiwoom | 개별 종목 가격 |
| FactSet SYM_V1 | FDR listing + pykrx ticker + DART corp_code | 티커 해상 |
| FactSet FF_V3 | OpenDartReader/OpenDART + FMP free | 펀더멘털 |
| FactSet FE_V4 | FMP free + manual consensus + broker report parsed summary | 추정치 |
| FactSet OWN_V5 | DART 지분공시 + FMP holders/ETF free 가능분 | 오너십 |
| CIQKEYDEV | DART 주요사항 + Naver News + RSS + SEC 8-K | 이벤트 |
| MT/StreetAccount | Naver News/RSS/Tavily | 뉴스 |
| Manticore/OpenSearch | local document_chunks.jsonl + SQLite/duckdb 추후 | 문서 검색 |

## 4. Kiwoom API 반영

키움은 무료로 쓸 수 있는 강력한 한국 주식 실시간/분봉 원천이지만, 다음 제약이 있다.

- OpenAPI+는 Windows/ActiveX/OCX 기반 제약이 있다.
- 32-bit Python/PyQt 환경이 필요한 레거시 패턴이 많다.
- REST/WebSocket API는 별도 API 포털/계정/사용신청이 필요할 수 있다.
- 실시간 데이터는 분석 DB에 직접 쓰지 말고 `quote_snapshot`과 `intraday_bar_cache`로 먼저 저장한다.

따라서 MVP에서는 Kiwoom을 optional adapter로 두고, 기본 데이터는 pykrx/FDR/OpenDartReader/ECOS로 구성한다.

## 5. 최소 구축 파일

- `master/company_master.csv`
- `master/symbol_aliases.csv`
- `master/peer_groups.csv`
- `prices/price_daily.csv`
- `prices/quote_snapshot.csv`
- `fundamentals/financials_annual.csv`
- `fundamentals/financials_quarterly.csv`
- `estimates/consensus_snapshot.csv`
- `valuation/valuation_snapshot.csv`
- `macro/sector_indicators.csv`
- `events/events.jsonl`
- `portfolio/portfolio_positions.csv`
- `risk/risk_limits.csv`

## 6. 증권분석 보고서 연결

SecurityAnalysisEngine은 위 데이터셋을 읽어 다음 분석을 계산한다.

1. Earnings driver
2. Margin/ROE trend
3. Estimate revision
4. Valuation premium/discount
5. Sector cycle signal
6. Evidence/counter-evidence weight
7. Portfolio impact
8. Risk budget/limit status
9. Final PM decision
