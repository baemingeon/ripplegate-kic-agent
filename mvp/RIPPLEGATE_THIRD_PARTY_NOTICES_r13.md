# RippleGate r13 외부 자료·모델 경계 고지

## 공개 snapshot에 사용한 자료

- UN Trade and Development (UNCTAD) 공개 statement: 해상 운송 경로와 항해기간 관련 관찰 근거
- U.S. Energy Information Administration (EIA) 공개 자료: Brent 가격 맥락
- UN Comtrade 공개 API query reference: URL·쿼리 메타데이터만 사용하며 원시 응답 금액·수량은 재배포하지 않음

각 자료의 URL·수집일·검증 상태는 `data/ripplegate_public_graph_v1.json`의 Evidence Ledger에 기록한다. 공개 snapshot은 운영용 최신 feed나 기관 승인 vendor 데이터로 자동 승격하지 않는다.

## 모델·런타임 경계

기본 실행은 외부 LLM 없이 결정론적 fallback으로 끝까지 재현된다. 승인된 private gateway를 연결하는 경우에도 LLM은 계획·질의·설명만 제안하며, 숫자·근거 상태·HOLD 판정은 코드와 독립 Critic이 담당한다. 공개 패키지에는 API key, 내부 문서, 개인정보, 특정 모델 실행 로그를 포함하지 않는다.

## 운영 전환

실제 기관 적용 전에는 자료 라이선스, 승인된 데이터 adapter, SSO/OIDC, TLS/WAF, DLP, secret 관리, 로그 접근통제 및 독립 보안검토를 별도로 완료해야 한다.

