# Third-party notices v0.9.0

## 공개 release에 포함된 외부 자료

### SEC EDGAR data APIs

- Source: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
- Use: public Company Facts와 filing-period metadata
- Controls: User-Agent, fair-access/rate limits, SEC Privacy and Security Policy, retrieval time/source URL

### Yahoo Finance snapshot

- Source: https://finance.yahoo.com/quote/MA/history/
- Terms: https://legal.yahoo.com/us/en/yahoo/terms/otos/index.html
- Scope: 공개 demo용 historical close snapshot. 운영 전환 전 승인된 시장데이터 vendor 또는 거래소 feed로 교체합니다.

## 모델·런타임 정책

공개 release는 특정 모델의 실행 결과에 의존하지 않습니다. 기본 경로는 모델 없이 실행하며, 승인된 private endpoint만 allowlist를 통과한 경우에 선택적으로 연결합니다. 특정 모델의 benchmark 로그와 모델 카드는 공개 release에서 제외했습니다.

## Original work and excluded material

- 투심렌즈 state workflow, goal router, typed Tool contract, 결정론적 Calculator/Verifier, evidence fingerprint, 투자심의팩 UI, benchmark harness, allowlist 정책, release packaging은 본 프로젝트의 작업입니다.
- 공개 release에는 KIC 내부 문서, API key, 개인정보, 비공개 시장데이터 feed를 포함하지 않습니다.
