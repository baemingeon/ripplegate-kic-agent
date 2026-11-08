# IC Preflight MVP release manifest v0.9.2

투자심의 전, 자료·수치·리스크의 빈틈을 확인하고 `투자심의팩`을 만드는 공개자료 기반 MVP입니다. IC Preflight는 KIC의 공개 투자 프로세스를 대체하지 않고, 위원회 검토 전 자료 품질과 계산 정합성을 확인하는 보조 레이어입니다.

## 공개 release 범위

- `server.py`, `llm_adapter.py`, `static/index.html`
- `Dockerfile`, `.dockerignore`, `render.yaml`, `DEPLOYMENT.md`
- `README.md`, `JUDGE_REPRO.md`, `DEMO_RUNBOOK.md`, `RELEASE_MANIFEST_v0.9.2.md`, `THIRD_PARTY_NOTICES_v0.9.2.md`
- 테스트·검증: `test_mvp.py`, `validate_release.py`, `validate_public_submission.py`, `benchmark.py`, `measure_effect.py`, `validate_effect_measurement.py`, `generate_pilot_artifacts.py`
- 공개자료·합성 benchmark·관측 신호 정책(`benchmark_observations_v1.json`)·자연어 라우팅 holdout·재현성 summary·효과 측정 template·빈 paired 측정표
- 정상·보류·기간 불일치·자료 부족 UI 결과 이미지

공개 ZIP에는 특정 국가의 공개 모델 실행 로그, API key, 내부 문서, 개인정보를 포함하지 않습니다. 과거 비공개 모델 실험은 공개 release와 분리합니다.

## 기본 실행 정책

- 기본 모드는 `모델 없음 + typed Controller + 결정론적 Calculator/Verifier`입니다.
- LLM은 계획·질의·설명만 제안합니다. 기간·정의·단위·통화·계산·출처·최종 보류 판정은 결정론적 모듈이 담당합니다.
- 승인 LLM을 연결하려면 `KIC_LLM_POLICY=approved`, `KIC_LLM_PROVIDER`, `KIC_LLM_MODEL`, `KIC_LLM_ALLOWED_MODELS`를 모두 명시해야 합니다.
- allowlist에 없는 모델은 호출하지 않고 `model_not_allowlisted`로 fallback합니다.
- 내부자료는 승인된 private endpoint 경계 밖으로 보내지 않습니다.

## 데이터 경계

- SEC Company Facts는 User-Agent·fair-access·보안정책을 준수합니다.
- Yahoo close snapshot은 공개 demo 전용입니다. 운영 전환 전 승인 vendor·거래소 feed와 사용권을 확보해야 합니다.
- 실데이터 수집 전 `KIC_SEC_CONTACT`를 실제 연락처로 설정합니다.
- Agent runtime 시간은 서버 실행시간일 뿐, 분석가 시간절감으로 해석하지 않습니다.
- stress holdout은 `observable_policy_v1`의 관측 신호로 평가하며, 결정론적 통제군을 live LLM 일반화 성능으로 주장하지 않습니다.

## 실행

```powershell
python .\server.py
python .\test_mvp.py
python .\validate_release.py
```
