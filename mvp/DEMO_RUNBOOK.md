# RippleGate 본선 데모 런북 r13

목적: 심사위원이 90초 안에 `Planner → Tool → 사람 Gate → FactGate → 계산 → Critic → REPLAN/HOLD → Review Pack`을 직접 확인하도록 현재 RippleGate MVP와 같은 실행 경로를 고정한다.

## 1. 시작

프로젝트 루트에서 실행한다.

```powershell
cd ".\mvp"
& .\run_ripplegate_demo.ps1
```

브라우저에서 `http://127.0.0.1:8766`을 연다. 기본 데이터는 `public_snapshot`이며, 모델과 외부 실시간 API 없이 재현된다.

## 1-보충. 선택적 typed LLM trace

본선에서 Agent의 실제 모델 연동을 질문받으면 공개·합성 packet에 한정한 loopback trace를 별도로 실행한다. 이 경로는 공개 Demo의 기본 runtime이 아니며, 내부자료·개인정보·포트폴리오 context를 전송하지 않는다.

```powershell
$env:RIPPLEGATE_LLM_MODE = "approved"
$env:KIC_LLM_POLICY = "approved"
$env:KIC_LLM_PROVIDER = "openai_compatible"
$env:KIC_LLM_URL = "http://127.0.0.1:11434/v1"
$env:KIC_LLM_ALLOWED_HOSTS = "127.0.0.1"
$env:KIC_LLM_MODEL = "qwen2.5:14b"
$env:KIC_LLM_ALLOWED_MODELS = "qwen2.5:14b"
$env:KIC_LLM_API_KEY = "local-only"
$env:KIC_LLM_TIMEOUT = "60"
python .\ripplegate_llm_trace.py
```

기대 trace는 `approved_gateway_typed_proposal → Tool → HUMAN_GATE → FactGate HOLD → REPLAN → Calculator → Critic → Review Pack`이다. LLM은 Tool 후보·위험 flag·질문만 반환하고, 숫자·가정·판정·승인은 결정론적 모듈과 사람에게 남긴다. 모델과 실행 경계는 `data/ripplegate_llm_trace_local_2026-11-08.json`에 기록한다.

## 2. 90초 정상·보류 시연

1. 대표 질문을 그대로 두거나 다음 문장을 입력한다.

   > 홍해 항로 우회가 유럽 수입·제조업과 아시아 수출기업에 미치는 영향을 3개월 기준으로 확인해줘. 파급경로·추천 가정·근거 상태·보류 이유를 보여줘.

2. `Agent 분석 시작`을 누른다.
3. Planner가 목적·기간·대상·채널을 읽고 선택한 Typed Tool과 추천 가정을 먼저 보여준다.
4. `추천 가정 확인 → 계산 실행`을 누른다. 사람 확인 전에는 계산하지 않는다는 점을 말한다.
5. 결과 화면에서 `VERIFIED 1 / SCENARIO 1 / HOLD 1`을 보여준다.
6. `PUB-UNCTAD-001`의 HTTPS 원문 링크를 열어 관찰값과 Evidence Ledger ID가 연결된 것을 확인한다.
7. `PUB-COMTRADE-001`은 mapping이 미완료이므로 숫자를 만들지 않고 `REPLAN / HOLD`와 다음 자료 요청을 남긴다는 점을 보여준다.
8. `같은 입력 비교`를 열어 검색·요약 대조 경로는 source ID를 보존하지만 경로·상태·계산을 만들지 않고, RippleGate에는 경로·근거·상태·다음 행동이 남는 것을 보여준다. 이 비교는 정확도나 환각률 benchmark가 아니다.
9. `감사 로그 저장` 또는 `검토팩 저장`으로 결과의 재현 자료를 내려받는다.

## 3. 실패 경로 30초 시연

1. 데이터 packet을 `synthetic`으로 바꾼다.
2. `Agent 분석 시작 → 추천 가정 확인 → 계산 실행`을 반복한다.
3. 기간·근거 충돌 경로가 `FactGate HOLD`가 되고, Critic이 수치·HOLD·근거 ID 불변식을 확인하며, Planner가 다음 Tool 후보를 남기는 것을 보여준다.
4. 발표 문장: “RippleGate는 오류를 숨기지 않고, 해결 가능한 재조회와 사람이 확인해야 할 보류를 분리합니다.”

## 4. 심사위원 재현 명령

외부 네트워크나 브라우저 없이 핵심 결과를 확인한다.

```powershell
cd ".\mvp"
python .\ripplegate_judge_repro.py --dataset public_snapshot
python .\ripplegate_judge_repro.py --holdout
python -m unittest discover -s . -p "test_ripplegate.py" -q
```

기대 결과:

- `--holdout`: 10/10 controlled contract checks `PASS`. 이는 정확도·환각률·실제 업무효과 측정이 아니다. prompt injection은 알려진 패턴 격리 계약을 포함한다.

- `reproduction: PASS`
- `VERIFIED 1 / SCENARIO 1 / HOLD 1`
- HTTPS Evidence Ledger 존재
- 동일 입력 통제군 `path_count=0`, `numeric_result=null`
- 독립 Critic 및 REPLAN trace 존재

서버가 실행 중이면 HTTP 경계도 확인한다.

```powershell
python .\ripplegate_http_smoke.py --base-url http://127.0.0.1:8766
```

health·보안 헤더·data policy·plan·run·compare, 사람 확인 없는 계산 차단, 잘못된 Content-Type, 과대 요청 방어가 모두 PASS여야 한다.

## 5. 장애 fallback

- 서버 오류: 실시간 조작을 중단하고 동일 `public_snapshot` 녹화본과 Judge 재현 결과로 전환한다.
- 원문 URL 장애: 고정 snapshot의 기준일·URL·자료 상태를 보여주고 실시간 자료로 승격하지 않는다.
- 승인 LLM 장애: LLM을 켜지 않은 deterministic Planner로 전환한다.
- 사람 확인 누락: 계산을 실행하지 않고 `HUMAN_GATE` 대기 상태를 보여준다.

## 6. 발표에서 지킬 범위

- 영향지수는 주가·수익률·P&L 예측이 아니다.
- 공개 snapshot은 최신 실시간 vendor feed가 아니며, `REVIEW_REQUIRED` 상태로 표시한다.
- Comtrade reference-only 자료는 승인 adapter 전까지 무역 노출 계산에 사용하지 않는다.
- 자동 투자승인·거래·리스크 한도 변경은 실행하지 않는다.
- 실제 사용자 시간 절감률·정확도·환각률은 P01~P05 paired 측정과 실제 데이터 adapter 기반 holdout 전에는 발표하지 않는다. 현재 `--holdout`은 계약 안전성 검사일 뿐이다.
- 내부자료 연결은 private gateway, 문서 권한, DLP, 보존·삭제정책, 로그 접근통제와 보안검토 후에만 허용한다.
