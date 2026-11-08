# KIC AI Agent 공모전 1등 달성 운영판 v0.1

기준일: 2026-11-07
현재 기준본: 기획서·MVP v0.9.2
브랜드 기준: `IC Preflight (아이씨 프리플라이트)`; 이전 `투심렌즈`·`심의나침반` 문서는 역사적 작업본
목표: 예선에서 문제 적합성·Agent 설계·차별성·실현 가능성·활용성을 동시에 증명하고, 본선에서 실제 실행·신뢰성·사용성까지 같은 증거로 연결한다.

## 1. 한 문장 포지션

**IC Preflight는 KIC 공개 투자 프로세스를 대체하는 투자판단기가 아니라, 투자심의 전 자료·수치·리스크를 확인해 ‘진행·추가자료·보류’로 나누는 검증 Agent다.**

공개자료상 KIC는 투자실무위원회에서 투자안의 예상 수익·리스크를 심의하고, 리스크관리전문위원회에서 리스크 관련 사항을 심의·평가한다. IC Preflight는 이 공개된 구조의 내부 SOP를 재현한다고 주장하지 않고, 검토 전 검증 packet을 준비하는 업무 접점 가설로 제시한다.

출처:
- https://www.kic.kr/ko/investment/process
- https://www.kic.kr/ko/investment/risk-management
- https://www.kic.kr/annual-report/2025/ko/sub0209.html

## 2. 경쟁팀이 따라오기 어려운 핵심 증거

| 심사위원이 보는 질문 | IC Preflight의 증거 | 과장하지 않을 표현 |
|---|---|---|
| 단순 RAG와 무엇이 다른가? | 같은 기간 불일치 입력에서 일반 답변 `REVIEW`, IC Preflight `HOLD` | 특정 케이스·비교군에서 선택적 보류를 보였다 |
| 진짜 Agent인가? | 사용자 목표 라우팅, typed allowlist, Tool 사전·사후조건, REPLAN, HOLD trace | 자유 실행이 아니라 안전한 조건부 자율성이다 |
| 숫자를 믿을 수 있는가? | 원문 메타데이터, 기준일·정의·단위 상태, Decimal 계산, SHA-256 fingerprint | 판정 근거와 계산 경로를 재현 가능하게 남긴다 |
| 모델이 없어도 되는가? | 결정론적 Controller·Calculator·Verifier·fallback | LLM은 제안, 최종 안전 게이트는 규칙·사람이다 |
| 실제 업무에 쓸 수 있는가? | 1페이지 심의팩, 다음 행동, 추가자료·보류 이유, human gate | 내부 SOP와 시간절감은 실측 전 가설이다 |

## 3. 예선 만점에 접근하는 증명 순서

1. 문제: 기간·정의·단위·가격 기준일이 다른 자료가 그럴듯한 심의 답변으로 이어지는 위험을 먼저 제시한다.
2. KIC 접점: 공개된 투자실무위원회·리스크관리전문위원회 검토 전 품질 게이트라는 가설을 명시한다.
3. Agent: 요청 목적을 읽고 경로를 선택한 뒤, Tool 계약을 검사하고 조건이 충족된 Tool만 호출한다.
4. 차별성: VERIFY 실패 후 REPLAN을 거쳐도 문제가 해소되지 않으면 계산을 완성하지 않고 HOLD한다.
5. 실현 가능성: 기업 1개·Peer 3개·공개 snapshot·멀티플·심의팩으로 범위를 고정하고, 모델 없는 PC 실행을 기본 경로로 둔다.
6. 활용성: 자료 조회·정규화·근거 ledger·승인 기록은 재사용하고, 자산군별 Adapter·지표 사전·권한 정책만 교체한다.

## 4. 본선 10분 데모 큐

| 시간 | 장면 | 반드시 보일 것 |
|---:|---|---|
| 0:00–0:35 | 기간 불일치 Hook | “그럴듯한 답보다 기준이 맞는 답이 먼저다” |
| 0:35–2:10 | 입력·정상 실행 | 사용자 목표, 자동 라우팅, 공식자료, Peer screen, 심의팩 |
| 2:10–4:00 | Agent trace | PLAN → Tool → NORMALIZE → VERIFY → CALCULATE |
| 4:00–5:15 | 재계획 | VERIFY fail → REPLAN → 원문 재조회 → 조건 재검사 |
| 5:15–6:05 | 보류 | 계산 Tool 사전조건 차단, HOLD, 담당자 다음 행동 |
| 6:05–7:05 | 신뢰성 | Evidence Ledger, 원문 링크, 기준일·정의·fingerprint |
| 7:05–8:00 | 평가 | base와 stress holdout, 반복 일치, false-hold 분리 |
| 8:00–9:10 | 운영·보안 | 승인 모델·private endpoint·권한·보존정책·fallback |
| 9:10–10:00 | Closing | 근거·재현·보류의 세 가지 차별점 |

심사위원 재현 입력은 홍보 문구가 아니라 고정된 테스트 케이스다.

> 대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘

## 5. 반드시 준비할 실측 증거

| 게이트 | 최소 기준 | 증거 파일 |
|---|---|---|
| 업무효과 | 동일 packet 5건 이상, 수작업·Agent 시간과 재작업을 같은 범위로 측정 | stopwatch raw log, `effect_measurement_summary` |
| 일반화 | 신규 기업 3–5개, 표현이 다른 오류·정상 케이스 분리 | holdout JSON, false-hold 표 |
| 실행 | GitHub fresh clone, 공개 Demo URL, 녹화 fallback의 결과 일치 | README, URL smoke log, video |
| 신뢰성 | source·period·metric·계산식·판정 연결 | Evidence Ledger, audit JSON |
| 운영 | 모델 장애·API 지연·부분자료에서도 안전 경로 유지 | fallback trace, failure log |

측정 전에는 시간절감률·내부 오류율·KIC SOP를 주장하지 않는다. 특정 모델의 로컬 실행 결과는 공개 release에서 제외하고, 모델 없는 baseline·observable policy 통제군과 실제 paired 측정만 사용한다.

## 6. 레드팀 질문에 대한 답변 원칙

- “전부 HOLD하면 100% 아닌가?” → 정상 케이스 false-hold를 별도로 측정하며 목표는 보류율이 아니라 선택성이다.
- “같은 LLM이 검증하는 것 아닌가?” → LLM은 계획·설명만 제안하고 Decimal Calculator·typed Verifier·human gate가 판정한다.
- “오류를 주입했으니 당연히 잡는 것 아닌가?” → 오류 주입군과 신규 표현 holdout을 분리하고 hand-authored control의 한계를 공개한다.
- “중국산 모델을 쓰는가?” → 공개 기본 경로는 모델 없이 실행하며, 승인 LLM도 allowlist와 private endpoint를 통과해야 한다. 공개 release에는 특정 모델 실행 로그를 넣지 않는다.
- “컴퓨터 사양이 부족하면?” → 모델 없는 안전 게이트를 기본으로 하고, 승인 모델은 연결 가능한 Adapter로 분리한다.
- “통화가 다르면 임의로 환산하는가?” → 아니다. 승인된 환율 snapshot의 기준일·출처가 없으면 환산과 valuation을 차단하고 `HOLD`로 담당자에게 넘긴다.
- “KIC 내부 업무를 재현했는가?” → 아니다. KIC 공개자료에 연결한 MVP 업무 가설이며, 실제 SOP·시간·오류율은 확인 전이다.

## 7. 현재 상태와 남은 잠금

완료된 증거:

- v0.9.2 PPTX 10장·PDF 10페이지
- MVP ZIP 44개 항목, fresh extract `READY`
- typed Tool 계약, 자동 라우팅, REPLAN/HOLD, 결정론적 fallback
- UI·API·공개 snapshot·검증 로그·시연영상 초안
- 로컬 `ic-preflight-case.v1` packet 입력, 스키마 거부, 담당자용 심의팩 Markdown 저장
- P01~P05 파일럿 manifest와 Agent-only runtime evidence 생성기
- paired 측정표·준비도 검증기·레드팀 Q&A를 연결해 사람 효과 수치의 임의 생성을 차단
- 다른 표현의 사용자 목표 12개를 모델 없이 같은 안전 경로로 라우팅하는 holdout 통제군과 반복 검증
- 통화 불일치 입력에서 환율 기준일·출처가 없으면 valuation을 차단하는 `HOLD` trace·UI·재현 카드를 추가

사용자 입력 후 잠글 항목:

- 팀명·팀장·팀원·연락처
- 실제 Demo URL·GitHub URL
- 실제 사용자 또는 packet 기반 효과 측정
- 본선용 신규 기업·신규 오류 holdout

현재 검증 상태가 `READY_AFTER_USER_INPUT`인 것은 코드 실패가 아니라 위 외부 입력이 아직 없기 때문이다.

효과 측정 전용 잠금: `mvp/validate_effect_measurement.py --strict`가 `READY_TO_REPORT`를 반환하기 전에는 시간절감률을 발표하지 않는다. 현재는 실제 사람 stopwatch가 없으므로 `AWAITING_HUMAN_PAIRING`이 정직한 상태다.

## 8. 절대 금지

- “KIC 공개 프로세스보다 우수하다” 대신 “공개 프로세스 앞단의 검증 계층”이라고 말한다.
- “100% 정확도·100% 탐지·시간 80% 절감”을 실측 없이 쓰지 않는다.
- 실제로 접속하지 않은 Demo·GitHub·데이터 라이선스를 기재하지 않는다.
- 모델 이름을 숨기거나 내부자료가 외부 API로 나가는 경로를 허용하지 않는다.
- 화면을 채우기 위해 본문 글자를 과도하게 축소하지 않는다.
