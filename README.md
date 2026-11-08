# IC Preflight (아이씨 프리플라이트)

투자심의 전, 숫자와 근거가 맞는지 확인하는 Agent

IC Preflight는 KIC의 투자 프로세스나 사람의 최종 판단을 대체하지 않습니다. 공개자료 기반으로 기업·Peer 자료의 기간, 정의, 단위, 통화, 기준일과 출처를 확인하고, 문제가 남으면 계산을 멈춘 뒤 `진행`, `추가자료`, `보류` 중 하나의 투자심의팩을 사람에게 넘기는 품질 게이트입니다.

## 1분 실행

PowerShell에서 저장소 루트 기준으로 실행합니다.

```powershell
python .\mvp\server.py
```

브라우저에서 `http://127.0.0.1:8765`를 열고 `자동 확인` 상태에서 다음 문장을 입력합니다.

> 대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘

기대 결과는 기간 불일치 확인, 원문 재조회, 보정 근거가 없으면 `HOLD`입니다. 검증 전 계산은 실행하지 않습니다.
실행이 끝나면 담당자 전달용 `투자심의팩` Markdown과 재현용 감사 로그 JSON을 각각 저장할 수 있습니다.
고정 예시 외 자료는 `mvp/data/case_packet_template.json` 형식의 로컬 JSON packet으로 재실행할 수 있습니다.

통화가 섞인 자료는 승인된 환율 기준일·출처가 없으면 자동 환산하지 않고 `currency_alignment_unresolved → HOLD`로 중단합니다.

## Agent 구성

```text
사용자 목표
    ↓
Typed Controller ── 허용 Tool 선택·사전조건·사후조건
    ↓
자료 조회 → 기준 맞추기 → 계산 → 검증·반대 검토
    ↓                         ↘ 문제 미해결: 추가자료 / HOLD
투자심의팩 + Evidence Ledger + 감사 로그 + 담당자 handoff
```

- Planner: 승인된 경우 다음 확인 단계와 설명을 제안합니다.
- Retriever/Adapter: 공개자료 snapshot 또는 승인된 데이터 연결부를 사용합니다.
- Normalizer: 기간·정의·단위·통화를 구조화합니다.
- Calculator: Decimal 기반으로 valuation과 민감도를 계산합니다.
- Verifier/Critic: 불일치, 누락, 오래된 가격, Peer 오류를 확인합니다.
- Human handoff: 모든 종료 경로에 담당자 확인 지점을 남깁니다.

LLM은 계획·질의·설명 제안만 담당합니다. 숫자, 출처, 계산, 최종 HOLD는 결정론적 모듈이 담당합니다.

## 모델·보안 경계

기본 실행은 모델이 없어도 동작합니다. 승인 LLM을 연결할 때는 `KIC_LLM_POLICY=approved`, provider, model, `KIC_LLM_ALLOWED_MODELS`를 명시해야 하며 allowlist 밖의 모델은 네트워크 호출 전에 거부합니다. 내부 문서와 비공개 투자정보는 승인된 private endpoint 밖으로 보내지 않습니다.

```powershell
$env:KIC_LLM_POLICY = "approved"
$env:KIC_LLM_PROVIDER = "openai_compatible"
$env:KIC_LLM_URL = "https://approved-private-gateway.example/v1"
$env:KIC_LLM_MODEL = "approved-model-name"
$env:KIC_LLM_ALLOWED_MODELS = "approved-model-name"
$env:KIC_LLM_API_KEY = "secret-store-value"
python .\mvp\server.py --warmup
```

## 검증

```powershell
python .\mvp\test_mvp.py
python .\mvp\validate_submission.py
```

`mvp/JUDGE_REPRO.md`는 심사위원 재현 절차를, `mvp/DEMO_RUNBOOK.md`는 90초 시연 순서를 설명합니다. 공개 release의 별도 검증은 `mvp/validate_release.py`로 실행합니다.

## 데이터·한계

- SEC Company Facts와 공개 IR·시장자료 snapshot을 사용합니다.
- Yahoo close snapshot은 demo 전용이며 운영 전환 전 승인 vendor로 교체해야 합니다.
- 현재 release는 공개자료와 합성 오류 케이스를 사용하며 KIC 내부 SOP를 재현한다고 주장하지 않습니다.
- 서버 실행시간은 분석가의 시간절감이 아닙니다. 동일 packet의 실제 stopwatch와 review log가 확보되기 전에는 효과 수치를 발표하지 않습니다.

## 제출용 파일

- 예선 기획서: `기획서/KIC_AI_에이전트_공모전_기획서_작업본_v0.9.2.pdf`
- 본선 MVP: `기획서/KIC_ICPreflight_MVP_v0.9.2_20261107.zip`
- 최신 안내: `기획서/최신본_사용안내_v0.9.2.md`

본 저장소에는 API key, 내부 문서, 개인정보를 넣지 않습니다. 외부 자원과 라이선스는 `mvp/THIRD_PARTY_NOTICES_v0.9.2.md`와 `mvp/data/source_policy_2026-11-07.json`에 기록합니다.
