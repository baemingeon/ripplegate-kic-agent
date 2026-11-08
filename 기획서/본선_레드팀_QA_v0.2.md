# IC Preflight 본선 레드팀 Q&A v0.2

목적: 심사위원의 날카로운 질문에 과장 없이 답하고, 답변을 실제 실행 증거로 연결한다.

## 1. “전부 보류하면 100% 아닌가요?”

답변: 전부 보류가 목표가 아니다. 정상 packet P01·P04·P05는 `REVIEW`, 기간 불일치 P02는 `HOLD`, 필수 근거 누락 P03은 `REQUEST_INFO`로 분리한다. 정상 케이스를 불필요하게 멈추는 false-hold를 별도로 기록하고, `mvp/validate_effect_measurement.py`는 paired 측정 전 업무효과를 주장하지 않도록 막는다.

보여줄 증거: `mvp/data/pilot_packet_manifest_v0.1.json`, `mvp/data/pilot_agent_runtime_2026-11-07.json`, 실행 화면의 `진행/추가자료/보류` 분기.

## 2. “같은 LLM이 추출하고 검증하면 독립 검증인가요?”

답변: IC Preflight의 기본 경로에는 LLM이 없어도 된다. LLM이 연결되어도 Planner·설명 제안만 담당하고, 기간·정의·단위·계산·최종 보류 판정은 typed Controller·Decimal Calculator·결정론적 Verifier·사람 승인으로 분리한다. 따라서 ‘같은 LLM의 자기검증’에 신뢰성을 의존하지 않는다.

보여줄 증거: `mvp/JUDGE_REPRO.md`, `mvp/data/model_policy_2026-11-07.json`, 감사 로그의 `planning_history`와 `human_gate_recorded`.

## 3. “오류를 직접 주입했으니 잡는 게 당연한 것 아닌가요?”

답변: 맞다. 합성 오류 주입은 안전 게이트의 동작을 보여주는 통제군일 뿐, 일반화 성능의 증거가 아니다. 그래서 정상 케이스 false-hold와 표현을 바꾼 신규 holdout을 분리하고, 발표에는 케이스 수·정책·반복 결과를 함께 공개한다. 처음 보는 자료는 해결되지 않으면 보류하지만, 보류율과 탐지율은 실제 holdout 측정 없이는 주장하지 않는다.

보여줄 증거: `mvp/data/benchmark_observations_v1.json`, `benchmark_holdout20_offline_result.json`, `benchmark_holdout20_offline_repeat01_result.json`.

## 4. “분석가가 실제로 몇 분 줄어드나요?”

답변: 아직 사람 stopwatch가 입력되지 않았다면 숫자를 말하지 않는다. 같은 `packet_id`의 수작업과 Agent end-to-end 기록을 P01~P05에 각각 남긴 뒤, 중앙값·범위·재작업·출처 누락을 함께 보고한다. 서버 실행시간은 사람 시간절감이 아니다.

보여줄 증거: `mvp/data/pilot_measurement_sheet_v0.2.json`, `mvp/validate_effect_measurement.py`, `기획서/본선_효과측정_프로토콜_v0.1.md`.

## 5. “내부 자료를 외부 API에 보낼 수 있나요? 중국산 모델을 쓰나요?”

답변: 공개 MVP의 기본 경로는 모델 없이 실행된다. LLM을 붙이는 경우에도 기관 승인 private gateway와 model allowlist를 통과한 경우만 Planner·Critic 제안에 사용하며, 내부자료는 승인된 반출·보존·접근권한 정책 밖으로 보내지 않는다. 특정 국가의 모델을 공개 기본값이나 필수 구성으로 두지 않는다. 이것은 보안 승인을 대체하는 주장도 아니다.

보여줄 증거: `mvp/data/model_policy_2026-11-07.json`, `mvp/data/source_policy_2026-11-07.json`, `mvp/README.md`의 모델·보안 정책.

## 답변 톤 규칙

- “KIC보다 우수하다”가 아니라 “KIC 공개 프로세스 앞단에 붙이는 검증 레이어”라고 말한다.
- “100% 정확도·시간 80% 절감” 대신 측정 조건과 현재 미측정 상태를 말한다.
- 실제 KIC 내부 SOP·비공개 문서·효과를 확인하지 않았다면 가정으로 표시한다.
