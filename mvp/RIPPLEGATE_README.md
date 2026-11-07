# RippleGate MVP

RippleGate는 글로벌 이슈 발생 직후 글로벌 매크로·멀티에셋 투자/리스크 분석 담당자가 쓰는 `영향 경로 → Agent 추천 가정 → 사람 확인 → FactGate 선검증 → 통과 경로 계산 → 투자검토팩` Agent입니다. 기본 화면은 공식 공개자료를 고정한 `public_snapshot`이며, 합성 packet은 오류·보류 경로 재현용으로 선택할 수 있습니다.

기존 FactGate 기업 분석 MVP와 분리된 실행 경로입니다.

참고: 같은 폴더에 남아 있는 `server.py`, `run_demo.ps1`, `test_mvp.py` 등은 이전 FactGate 작업 기록이다. 현재 RippleGate 실행·검증·공개 source 경로는 `ripplegate_server.py`, `run_ripplegate_demo.ps1`, `test_ripplegate.py`다.

공개 Demo: https://ripplegate-kic-agent.branchingdonkey2.chatgpt.site

공개 Demo는 브라우저 정적 adapter로 동일한 public/synthetic packet과 FactGate·독립 Critic 흐름을 재현합니다. 실시간 시장 API·내부자료·자동 투자판단을 제공하지 않습니다.

## 실행

```powershell
cd "C:\Users\bmg37\kic 국부펀드\mvp"
& .\run_ripplegate_demo.ps1
```

브라우저에서 `http://127.0.0.1:8766`을 엽니다.

90초 본선 시연 순서는 [`DEMO_RUNBOOK.md`](DEMO_RUNBOOK.md)에 고정했습니다. 현재 RippleGate 실행 경로와 다른 예전 FactGate 런북은 제출 경로에서 사용하지 않습니다.

1. 사용자 목적을 그대로 입력하거나 기본 목적을 사용하고 `Agent 분석 시작`을 누릅니다.
2. Planner가 목적에 따라 선택한 Tool과 충격·전가율·노출도 추천값을 확인합니다.
3. 기본값을 그대로 두거나 예외값만 수정하고 `추천 가정 확인 → 계산 실행`을 누릅니다. 실행 순서는 `FactGate 선검증 → 통과 경로만 계산`이며, HOLD 경로는 계산하지 않습니다.
4. 경로별 영향 범위, `VERIFIED / SCENARIO / HOLD`, 클릭 가능한 Evidence Ledger 원문 링크, `REPLAN / HOLD` trace를 확인합니다.
5. 감사 로그 JSON 또는 사람 검토용 Markdown을 저장합니다.

기본 Planner는 고정된 전체 파이프라인을 무조건 실행하지 않습니다. 사용자 목표의 이슈·노출·시장·계산 신호를 읽어 필요한 Typed Tool만 선택하고, 근거 검증·사람 게이트·검토팩은 항상 유지합니다. 예를 들어 원문·기준일 확인만 요청하면 계산 Tool을 선택하지 않습니다.

포트폴리오 편입·비중·집중도·한도 확인을 요청하면 `portfolio_context_lookup`이 계획에 추가됩니다. 승인된 `ripplegate-portfolio-context.v1` context가 없으면 실행 결과는 `REQUEST_INFO`로 종료되고 포트폴리오 영향·P&L을 계산하지 않습니다. 화면의 `합성 Portfolio context로 시연` 버튼은 3% 제안 비중·10% 현재 노출·15% 한도를 가진 workflow rehearsal이며, 결과는 실제 수익률이 아닌 `포트폴리오 민감도 지수`입니다.

API와 화면은 자료 품질 경계도 함께 반환합니다. 공개 snapshot은 `REVIEW_REQUIRED`로 표시되고 `not_loaded`·미연결 source는 계산에서 제외됩니다. 합성 packet은 `CONTROLLED_DEMO`로 표시되며 실제 시장자료·기관 운영자료로 승격하지 않습니다. 각 Evidence Ledger 항목에는 자료유형·기준기간·수집일·검증상태가 남습니다.

같은 입력 비교 화면은 요약형 통제군과 RippleGate를 나란히 보여줍니다. 통제군은 경로·숫자·상태를 확정하지 않으며, 이 비교는 정확도·환각률 벤치마크가 아니라 업무 구조 차이를 재현하는 용도입니다.

심사위원 재현 명령:

```powershell
python .\ripplegate_judge_repro.py --dataset public_snapshot
```

기대 판정은 `VERIFIED 1 / SCENARIO 1 / HOLD 1`이며, Planner·Tool·Human Gate·Calculator·FactGate·독립 Critic·REPLAN·Review Pack trace와 HTTPS Evidence Ledger, 동일 입력 통제군 결과가 출력됩니다.

## 데이터 packet

- `public_snapshot`: UNCTAD 공개 statement의 항해기간 관찰값과 EIA의 Brent 공개 snapshot을 사용합니다. UN Comtrade는 한국-사우디 HS 2709 query의 URL·메타데이터만 참조하며 원시 응답 금액·수량은 공개 패키지에 재배포하지 않습니다. 추가 국가·품목 mapping이 아직 승인·라이선스된 adapter로 연결되지 않은 경로는 의도적으로 `HOLD`입니다.
- Comtrade의 `PUB-COMTRADE-002`는 query reference-only 항목이고, `PUB-COMTRADE-001`은 필요한 전체 mapping 기준 source입니다. 두 항목 모두 승인·라이선스된 adapter가 연결되기 전까지 전체 무역노출 수치를 계산하지 않습니다.
- `synthetic`: 기간 충돌이 포함된 합성 packet으로 FactGate의 오류 대응을 재현합니다.
- 공개자료는 운영 vendor 데이터나 최신 실시간 feed로 자동 승격하지 않습니다.

## 안전 경계

- 기본 public snapshot은 공식 공개자료의 고정 snapshot이며, `synthetic` 선택 시에만 `mvp/data/ripplegate_demo_graph_v1.json`을 사용합니다.
- 숫자는 투자수익률 예측이 아니라 `충격 × 전가율 × 노출도`로 만든 영향지수 시연입니다.
- 모든 영향 계산은 사람이 확인한 가정으로만 실행됩니다.
- 기간이 충돌한 경로는 가정을 만들거나 단일 숫자를 만들지 않고 `HOLD`합니다.
- LLM·외부 API 없이도 전체 흐름을 재현할 수 있도록 결정론적 정책을 사용합니다.
- 승인된 private/OpenAI-compatible gateway를 연결할 때만 Planner 제안 모드를 켤 수 있습니다. LLM은 Tool 후보·위험 flag만 반환하고 숫자·가정·판정은 반환할 수 없으며, unknown Tool이면 결정론적 fallback으로 돌아갑니다.
- 자동 매매·자동 투자승인·리스크 한도 변경은 실행하지 않습니다.

보안 위협·통제·운영 전환 조건은 `RIPPLEGATE_SECURITY.md`에 정리했습니다. MVP의 회귀 테스트는 prompt injection 출력 경계, 출처 URL allowlist, 미검증 자료 HOLD, 사람 확인 전 계산 차단, Evidence Ledger 원문 링크 계약, 독립 Critic의 수치·HOLD·근거·Tool 불변식 검사를 포함합니다.

실제 사용자 효과는 임의 수치로 채우지 않습니다. `RIPPLEGATE_PAIRED_EVAL.md`와 `ripplegate_paired_eval.py`는 P01~P05에서 수작업 stopwatch와 Agent end-to-end stopwatch를 각각 실제로 확인하고, review log·trace·Evidence Ledger가 모두 갖춰진 경우에만 paired 기록을 남기도록 설계했습니다.

선택적 Planner 연결 예시:

```powershell
$env:RIPPLEGATE_LLM_MODE = "approved"
$env:KIC_LLM_POLICY = "approved"
$env:KIC_LLM_PROVIDER = "openai_compatible"
$env:KIC_LLM_URL = "https://approved-private-gateway.example"
$env:KIC_LLM_ALLOWED_HOSTS = "approved-private-gateway.example"
$env:KIC_LLM_MODEL = "approved-model-name"
$env:KIC_LLM_ALLOWED_MODELS = "approved-model-name"
$env:KIC_LLM_API_KEY = "주입된 secret"
```

## API smoke test

```powershell
python -c "import json,urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8766/health').read().decode())"
```

계획 생성:

```powershell
$body = '{\"phase\":\"plan\",\"event_id\":\"event_middle_east\",\"horizon_months\":3}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8766/api/analyze -ContentType 'application/json' -Body $body
```

정상·방어 경로를 한 번에 확인하려면 서버를 실행한 상태에서 다음 명령을 사용합니다.

```powershell
python .\ripplegate_http_smoke.py --base-url http://127.0.0.1:8766
```

컨테이너로 실행할 때는 현재 `ripplegate_server.py`를 사용합니다.

```powershell
docker build -t ripplegate-mvp .
docker run --rm -p 8766:8766 ripplegate-mvp
```

예선 제출 파일·레이아웃 receipt·MVP ZIP·팀 정보와 본선용 외부 링크/paired 측정 상태를 함께 확인하려면 저장소 루트에서 `python .\mvp\validate_ripplegate_submission.py`를 실행합니다. 이 명령은 관찰하지 않은 성과 수치를 만들지 않습니다.

## 본선 전 교체 대상

- 합성 source를 승인된 뉴스·시장·무역·포트폴리오 adapter로 교체
- source별 라이선스·기준일·갱신주기·장애 fallback 등록
- 실제 사용자 paired 측정과 오류 holdout 평가 추가
- 기관 배포에서는 SSO/OIDC, private model gateway, DLP, WAF, 로그 접근통제와 보안검토 추가
