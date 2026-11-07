# RippleGate r13 외부 자료·모델 경계 고지

작성 기준일: 2026-11-08

이 파일은 공모전 규정의 외부 자원 기록 요구에 맞춰 공개 실행 패키지의 자료 출처와 AI 사용 경계를 요약한다. 세부 관찰값·기준일·상태는 `data/ripplegate_public_graph_v1.json`의 Evidence Ledger에서 확인한다.

## 공개 snapshot에 사용한 자료

| 자료 | 원문·쿼리 | 이용조건·사용 범위 |
|---|---|---|
| UN Trade and Development (UNCTAD) 공개 statement | https://unctad.org/osgstatement/arria-formula-meeting-security-council-safe-seas-shared-security-protecting-freedom | https://unctad.org/terms · 짧은 관찰값·원문 링크·수집일만 기록하고 전문·이미지는 재배포하지 않음 |
| U.S. Energy Information Administration (EIA) Brent 공개 자료 | https://www.eia.gov/dnav/pet/hist/RBRTEw.htm | https://www.eia.gov/about/copyrights_reuse.php · 공개 snapshot의 관찰값·기간·출처만 사용하고 기업 손익으로 일반화하지 않음 |
| UN Comtrade 공개 API query reference | https://comtradeapi.un.org/public/v1/preview/C/A/HS | https://comtradeplus.un.org/LicenseAgreement · query URL·메타데이터만 남기며 원시 응답 금액·수량은 재배포하지 않음. 승인·라이선스된 adapter가 연결되기 전 무역노출 수치는 `HOLD` |

공개 snapshot은 운영용 최신 feed나 기관 승인 vendor 데이터로 자동 승격하지 않는다. 운영 전환 시 각 provider의 최신 약관·라이선스·갱신주기를 다시 확인한다.

## 모델·개발 도구·런타임 경계

- OpenAI Codex/ChatGPT 개발 보조 환경을 기획 문장·코드 초안·검토·테스트 보조에 사용했다. 최종 설계·수정·실행 검증은 참가자가 수행했으며, 내부 KIC 자료·개인정보·비공개 포트폴리오를 입력하지 않았다.
- Anthropic Claude의 사용자 제공 검토 의견은 초기 기획·점수·리스크 보완을 위한 개발 검토 보조로만 참고했다. 현재 runtime dependency나 Claude API 호출은 없으며, 최종 설계·코드·수치는 참가자가 검토·수정·실행 검증했다.
- 공개 MVP의 기본 실행은 외부 LLM 없이 결정론적 fallback으로 끝까지 재현된다. 공개 패키지에는 API key, 내부 문서, 개인정보, 특정 외부 모델 실행 로그가 없다.
- 승인된 private/OpenAI-compatible gateway를 연결하는 경우에도 LLM은 계획·질의·설명만 제안한다. 숫자·근거 상태·HOLD 판정은 코드와 독립 Critic이 담당하며, 모델·호스트 allowlist와 보안 승인을 먼저 통과해야 한다.
- Qwen/Ollama 등 과거 로컬 실험은 현재 제출물·성능 근거·공개 r13 runtime dependency에서 제외했다.

## 독창적 결합

외부 자료·AI를 그대로 복제하지 않고, 세계지도 사건을 typed impact path로 바꾸는 흐름, 사람 확인 전 계산 차단, Evidence Ledger, `VERIFIED / SCENARIO / HOLD`, Critic·REPLAN·Review Pack을 RippleGate 프로젝트에서 설계·구현했다.

## 운영 전환

실제 기관 적용 전에는 자료 라이선스, 승인된 데이터 adapter, SSO/OIDC, TLS/WAF, DLP, secret 관리, 로그 접근통제 및 독립 보안검토를 별도로 완료해야 한다. 공모전의 외부 자원 허용은 개인정보보호법·저작권·기관 보안정책을 대체하지 않는다.

공모전 규정: https://daker.ai/public/hackathons/kic-ai-agent-competition

