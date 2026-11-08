# 본선 데모 런북

## 90초 시연 순서

1. `python .\server.py --warmup`으로 로컬 서버를 시작하고 `http://127.0.0.1:8765`를 연다. warm-up 실패 시에는 `python .\server.py`로 재시작한다.
2. `실제 공개자료 snapshot · Mastercard`와 `모델 없이 안전 확인`을 선택한다.
3. 실행 화면에서 `자료 찾기 → 기준 맞추기 → 계산 → 검증 → 심의팩` 흐름과 투자심의팩을 먼저 보여주고, 심사위원이 원하면 `근거 목록과 상세 실행 기록 보기`를 연다.
4. 근거 목록의 SEC Company Facts 링크를 한 번 열어 원문 근거를 확인한다. Visa가 기간·필수지표 게이트에서 제외된 이유를 설명한다.
5. 같은 입력 H02를 가리킨다. 기록된 일반 답변 비교군은 REVIEW로 넘겼지만 관측 신호 기반 IC Preflight 정책은 기간 불일치를 HOLD한 기록이다.
6. 투자심의팩의 P/S median 3.60과 USD 118,047.6m 산출값을 보여주고, 매출 -10%·멀티플 -0.5x 민감도 미리보기는 리스크관리용 사전 점검이며 공통 EV 정의·라이선스 확인 전에는 승인하지 않는다고 말한다.
7. 실행시간·근거/조회/기록 개수를 확인하고 `투자심의팩 저장`으로 담당자 전달용 Markdown을, `감사 로그 저장`으로 재현용 JSON을 저장한다.
8. `기간 불일치 · 동일 입력 비교`로 바꾸어 실행한다. 동일 입력에서 기록된 일반 답변은 REVIEW였지만 IC Preflight는 기간 확인 단계에서 HOLD하는 비교 카드를 보여준다.
9. `수치 충돌 후 보류`로 바꾸어 재실행한다. VERIFY fail → REPLAN hold → IC 메모 보류를 보여준다.
10. `통화 불일치 · 환율 근거 확인`으로 바꾸어 실행한다. 같은 Revenue가 USD/EUR로 섞이면 VERIFY fail → 환율 기준 확인 → HOLD가 되고, 환율 근거 없는 환산을 하지 않는 것을 보여준다.
11. `필수 근거 부족 · 추가자료 요청`으로 바꾸어 실행한다. EBITDA가 빠진 상태에서 VERIFY fail → REPLAN retry → 추가자료 요청으로 이어지고, 계산은 실행되지 않는 것을 보여준다.
12. 승인 모델이 없거나 지연되면 `모델 없이 안전 확인`을 유지한다. 숫자 계산과 최종 보류 판정은 두 모드에서 동일하다.
13. 본선에서 같은 packet을 측정할 때는 `measure_effect.py`로 Agent 기록을 남기고, 분석가의 수작업 stopwatch 기록을 같은 `packet_id`로 입력한다.
14. 효과 수치를 넣기 전 `python .\validate_effect_measurement.py --strict`를 실행한다. `AWAITING_HUMAN_PAIRING`·`INCOMPLETE`이면 숫자를 발표하지 않는다.
15. 적용성 질문이 나오면 `data/case_packet_template.json`을 왼쪽 `분석 자료 묶음`에 선택하고, 고정 공개자료와 같은 검증 흐름으로 로컬 packet의 심의팩이 생성되는 장면을 보여준다.

심사위원 재현 문장은 `JUDGE_REPRO.md`에 고정되어 있다. `자동 확인`에서 `대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘`를 입력하면 Agent가 기간 불일치 경로를 선택하고, 기대 결과 `VERIFY fail → REPLAN → 원문 재조회 → HOLD`를 남긴다.

## 시작 전 30초 점검

`python .\validate_submission.py`를 실행해 PPTX/PDF, 반복성 로그, UI 실행 로그, clean/conflict/hold/period_mismatch/currency_mismatch/missing_evidence/real 경로를 확인한다. 결과가 `READY_AFTER_USER_INPUT`이면 표지 팀 정보와 본선 외부 제출 링크가 아직 사용자 입력 대기라는 뜻이다. 예선은 팀 정보 입력 후 제출하고, 본선 진출 시 링크 validator까지 실행한다.

## 발표에서 반드시 말할 경계

- 승인 LLM은 계획·질의·설명을 제안한다. LLM이 없어도 `typed_policy_v1` Controller가 허용된 Tool을 실행하며, 숫자 계산·기간·통화·단위·출처 게이트·최종 HOLD는 결정론적 모듈이 맡는다.
- Planner의 free-form Tool 제안은 `typed_allowlist_v1`로 축소한 뒤에만 public snapshot adapter로 실행된다. 등록되지 않은 Tool 이름은 실행되지 않는다.
- 공개 release의 benchmark는 모델 없는 offline proxy와 관측 신호 기반 정책 통제군이다. 특정 모델의 실행 결과는 공개 데모의 성능 근거로 사용하지 않는다.
- stress holdout은 `observable_policy_v1`의 관측 신호와 규칙으로 판정한다. 사전에 설계한 정책 통제군이므로 오류 정답을 미리 맞힌 AI 성능으로 포장하지 않는다.
- Mastercard snapshot은 공개자료 실험용이다. Yahoo Finance 시장데이터 라이선스와 실제 내부자료 반출 여부는 도입 전 검토한다.

## 예상 질문 답변

### “전부 HOLD하면 안전한 것 아닌가?”

정상 케이스를 함께 넣고 false-hold rate를 별도로 측정한다. 목적은 보류율을 최대화하는 것이 아니라 중대 오류만 보류하고 정상 케이스는 검토 가능한 상태로 보내는 것이다.

### “같은 LLM이 추출하고 검증하면 독립 검증인가?”

아니다. LLM은 Planner와 Reflection 역할만 수행하며, Decimal 기반 Calculator와 독립된 typed Verifier가 최종 게이트를 맡는다. 같은 LLM의 자기검증을 독립 검증으로 세지 않는다.

### “오류를 주입했으니 잡는 게 당연한 것 아닌가?”

오류 유형과 정답 라벨을 실행 코드에 넣지 않은 관측 신호 holdout 20건을 별도로 운영하고, 입력·정책 버전·실행일·반복 결과를 고정 보관한다. 다만 이 통제군은 사전에 설계한 결정론적 정책이므로 live LLM의 일반화 성능으로 과장하지 않는다.

### “분석가의 시간이 실제로 얼마나 줄어드나?”

아직 절감 시간을 주장하지 않는다. 동일한 입력 packet으로 수작업과 Agent 초안 작성 시간을 stopwatch로 각각 기록하고, 재작업 횟수·출처 누락·계산 불일치를 함께 비교한다.

### “내부 자료를 외부 API에 보낼 수 있나?”

MVP는 공개자료로 제한한다. 내부 도입은 private endpoint 또는 승인된 사내 모델, 문서별 접근권한, PII 비식별화, 보존·삭제정책을 통과한 뒤에만 연결한다.
