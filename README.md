# RippleGate — KIC AI Agent Competition public release

RippleGate는 글로벌 이슈를 투자 검토용 파급경로로 구조화하고, 근거·가정·검증 상태가 약한 경로는 `HOLD`로 멈추는 공개 MVP입니다.

## 실행

실행·재현 안내는 [`mvp/RIPPLEGATE_README.md`](mvp/RIPPLEGATE_README.md)와 [`mvp/DEMO_RUNBOOK.md`](mvp/DEMO_RUNBOOK.md)를 확인합니다.

```powershell
cd mvp
python .\ripplegate_server.py --host 127.0.0.1 --port 8766
python .\ripplegate_judge_repro.py --holdout
```

## 공개 범위

- 공개 snapshot과 합성 demo packet만 포함합니다.
- API key, 비밀번호, 팀 정보, 내부 문서, 비공개 포트폴리오는 포함하지 않습니다.
- 기본 실행 경로는 외부 LLM 없이 동작하며, 숫자·판정·승인은 결정론적 모듈과 사람에게 남깁니다.
- 외부 데이터·AI/API 사용조건과 출처는 `mvp/RIPPLEGATE_THIRD_PARTY_NOTICES_r13.md`에 기록합니다.
- `--holdout`은 10개 통제된 계약 위반을 모두 `HOLD` 또는 `REJECT`하는지 확인하며, 정확도·환각률·실제 업무효과 벤치마크가 아닙니다.

## 상태

공개 저장소: https://github.com/baemingeon/ripplegate-kic-agent

현재 `main`에는 RippleGate r13 공개 source가 push되어 있으며, 최신 커밋은 `3ab342d`입니다. 팀 개인정보·API key·내부 문서는 포함하지 않습니다.
