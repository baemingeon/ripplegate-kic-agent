# IC Preflight MVP

IC Preflight는 투자심의 전에 기업자료의 기간·정의·단위·통화·출처를 확인하고, 근거가 맞지 않으면 계산을 멈추는 검증 Agent입니다.

KIC의 공개 투자 프로세스를 대신하지 않습니다. 공개된 위원회 검토 전 단계에서 분석가가 심의자료를 준비할 때 쓰는 품질 확인 레이어라는 업무 가설을 구현합니다. 공개자료와 합성 오류 케이스만 사용하며 실제 투자판단에는 사용하지 않습니다.

## 가장 짧은 재현

```powershell
python .\server.py
```

브라우저에서 `http://127.0.0.1:8765`를 연 뒤 `자동 확인` 상태에서 다음 문장을 입력합니다.

> 대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘

기대 결과는 `기간 확인 실패 → 다시 확인 → 보류`입니다. 화면에는 일반 답변의 `REVIEW`와 IC Preflight의 `HOLD`, 보류 이유, 근거, 다음 행동이 함께 표시됩니다.

통화 검증은 확인 경로를 `통화 불일치 · 환율 근거 확인`으로 선택해 재현할 수 있습니다. `USD/EUR`가 섞이고 승인된 환율 snapshot이 없으면 환산과 valuation을 실행하지 않고 `HOLD`합니다.

## 사용자가 보는 흐름

1. 기업·기준일·검토 목적을 입력합니다.
2. Agent가 요청 신호에 맞춰 자료 조회와 검증 순서를 선택합니다.
3. 공식 원문과 시장자료를 Evidence Ledger에 연결합니다.
4. 기간·정의·단위·통화를 맞춘 뒤 계산과 반대 검토를 실행합니다.
5. 충돌이 생기면 원문 재조회·정의 정규화·재계산 중 필요한 단계로 계획을 바꿉니다.
6. `진행`, `추가자료`, `보류` 중 하나의 투자심의팩을 사람에게 넘깁니다.
7. 결과 화면에서 사람이 전달받을 `투자심의팩`과 재현 가능한 `감사 로그`를 각각 저장할 수 있습니다.

최종 투자 승인·거래 실행·리스크 한도 변경은 자동화하지 않습니다.

## 다른 기업 자료로 재실행

왼쪽 입력 화면에서 `mvp/data/case_packet_template.json`을 선택하면 고정된 공개 snapshot 대신 로컬 JSON packet을 같은 검증 흐름에 넣을 수 있습니다. packet은 `ic-preflight-case.v1` 계약, USD 금액, 기업 1개·Peer·근거 목록을 포함해야 하며, 파일은 브라우저에서 읽은 뒤 외부로 전송하지 않습니다. 서버는 실행 전에 필드·숫자·중복 ID·근거 구조를 다시 검사합니다.

## Agent 설계

- Planner: 승인된 경우에만 다음 확인 단계를 제안합니다.
- Typed Controller: 제안된 Tool을 allowlist로 줄이고 사전조건·사후조건을 검사합니다.
- Retriever: 공개자료 snapshot 또는 승인된 Adapter에서 근거를 가져옵니다.
- Normalizer: 기간·정의·단위·통화를 구조화합니다.
- Calculator: Decimal 기반으로 valuation과 민감도를 계산합니다.
- Verifier/Critic: 충돌과 보류 조건을 확인합니다.
- Human handoff: 모든 종료 경로에 담당자 확인 지점을 기록합니다.

LLM은 설명을 잘 쓰는 역할이고, 최종 숫자·출처·보류 판정은 결정론적 모듈이 맡습니다. 검증 전 계산은 실행하지 않으며, 모델이 실패해도 안전 게이트와 심의팩이 계속 동작합니다.
각 실행의 초기 계획과 재계획은 `planning_history`로 저장되며, 감사 로그에서 목적·선택 Tool·중단 조건을 다시 확인할 수 있습니다.

## 모델·보안 정책

기본 실행에는 모델이 필요 없습니다. `model_policy_2026-11-07.json`의 기준 PC에서 모델 없는 경로를 실행했습니다. 현재 PC에서 RTX 3050이 없어도 자료 snapshot, Controller, Decimal 계산, UI는 동작합니다.

LLM을 연결할 때는 승인된 모델을 명시적으로 allowlist에 등록해야 합니다.

```powershell
$env:KIC_LLM_POLICY = "approved"
$env:KIC_LLM_PROVIDER = "openai_compatible" # 승인된 private gateway
$env:KIC_LLM_URL = "https://approved-private-gateway.example/v1"
$env:KIC_LLM_MODEL = "approved-model-name"
$env:KIC_LLM_ALLOWED_MODELS = "approved-model-name"
$env:KIC_LLM_API_KEY = "주입된 secret"
python .\server.py --warmup
```

allowlist에 없는 모델은 호출하지 않습니다. 내부 문서와 비공개 투자정보는 승인된 private endpoint 경계 밖으로 보내지 않습니다. 공개 release에는 특정 모델의 실행 로그를 포함하지 않습니다.

## 실행·검증 명령

```powershell
python .\test_mvp.py
python .\validate_release.py
```

`test_mvp.py`는 clean, conflict, hold, period mismatch, currency mismatch, missing evidence, real 데이터 경로와 LLM 장애 fallback, 승인 gateway 계약을 검사합니다. `validate_release.py`는 별도 압축 해제 폴더에서도 같은 실행을 반복합니다.

`data/goal_route_holdout_v1.json`은 같은 목적을 서로 다른 문장으로 표현한 12개 라우팅 통제군입니다. 모델 없는 `route_user_goal`이 기간 불일치·자료 부족·충돌·보류·정상·공개자료 경로를 고정적으로 구분하는지 확인하며, live LLM 일반화나 실제 KIC 사용자 검증으로 과장하지 않습니다.

stress holdout 20건은 정답 판정을 코드에 넣지 않고 `data/benchmark_observations_v1.json`의 관측 가능한 기간·통화·단위·출처·가격·Peer·수식 신호를 `observable_policy_v1` 규칙으로 평가합니다. 이 결과는 결정론적 통제군의 재현성 증거이며 live LLM의 일반화 성능을 의미하지 않습니다.

브라우저 결과 캡처는 `assets/ui-real.png`, `assets/ui-hold.png`, `assets/ui-period-mismatch.png`, `assets/ui-currency-mismatch.png`, `assets/ui-missing-evidence.png`, `assets/ui-local-packet.png`에 있습니다. 각 근거에는 원문 metadata fingerprint가 남고, 투자심의팩 Markdown과 감사 로그 JSON을 각각 저장할 수 있습니다.

## 공개자료 조건

- SEC Company Facts: User-Agent와 fair-access 조건을 준수합니다. 실제 수집 전 `KIC_SEC_CONTACT`를 설정합니다.
- Yahoo close snapshot: 공개 demo 전용입니다. 운영 전환 전 승인 vendor 또는 거래소 feed로 교체합니다.
- 내부 KIC 문서·API key·개인정보는 release에 포함하지 않습니다.

```powershell
$env:KIC_SEC_CONTACT = "team-or-contact@example.com"
python .\fetch_real_case.py > .\real_case_snapshot.json
```

## 효과 측정

Agent 서버 실행시간을 분석가의 시간절감으로 주장하지 않습니다. 같은 `packet_id`를 수작업과 Agent로 각각 측정해야 합니다.

```powershell
python .\generate_pilot_artifacts.py
python .\measure_effect.py --condition agent --packet-id P01 --scenario period_mismatch
python .\measure_effect.py --condition summary --log .\data\effect_measurement_log.jsonl
python .\validate_effect_measurement.py
```

위 Agent 명령은 `server_runtime_only` 재현성 기록이다. 실제 효과를 측정할 때는 같은 `packet_id`에 분석가 stopwatch와 Agent end-to-end 시간을 각각 기록한다.

```powershell
# 아래 <...>는 실제 측정값으로 대체한다. 예시 숫자를 발표 자료에 사용하지 않는다.
python .\measure_effect.py --condition manual --packet-id P01 --scenario clean --elapsed-minutes <분> --rework-count <회> --source-gaps <건> --calculation-inconsistencies <건> --decision REVIEW
python .\measure_effect.py --condition agent --packet-id P01 --scenario clean --timing-scope end_to_end_workflow --observed-minutes <분>
python .\validate_effect_measurement.py --strict
```

검증 결과가 `AWAITING_HUMAN_PAIRING` 또는 `INCOMPLETE`이면 시간절감률을 발표하지 않는다. `READY_TO_REPORT`가 되어도 표본 5개 파일럿 결과로만 표시하며, 전체 업무효과로 일반화하지 않는다.

## 배포 경계

```powershell
docker build -t ic-preflight-demo .
docker run --rm -p 8765:8765 -e KIC_HOST=0.0.0.0 -e PORT=8765 ic-preflight-demo
```

Docker가 없는 환경에서는 `python .\server.py`로 먼저 실행합니다. 배포 전에는 인증, 접근권한, 로그 보존·삭제, 승인된 시장데이터와 모델 endpoint를 별도로 확정해야 합니다.
