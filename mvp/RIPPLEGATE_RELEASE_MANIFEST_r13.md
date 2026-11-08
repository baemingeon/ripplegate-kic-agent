# RippleGate MVP public snapshot r13

작성 기준일: 2026-11-08

공개 Demo: https://ripplegate-kic-agent.branchingdonkey2.chatgpt.site

## 이 패키지의 범위

r13은 실행과 재현에 필요한 현재 RippleGate 파일만 포함한 정리된 공개 snapshot이다. 과거 FactGate·로컬 모델·benchmark 실험·오래된 감사 결과는 포함하지 않는다.

- `ripplegate_server.py`: Planner fallback, Tool allowlist, Human Gate, FactGate, Calculator, 독립 Critic, REPLAN, Review Pack
- `ripplegate_static/index.html`: 세계지도·경로·Evidence Ledger·HOLD/REPLAN UI
- `DEMO_RUNBOOK.md`: 현재 r13과 일치하는 90초 시연·장애 fallback·재현 절차
- `Dockerfile`, `render.yaml`: 현재 `ripplegate_server.py`를 실행하는 컨테이너 배포 경로
- `data/ripplegate_public_graph_v1.json`: 공개자료 snapshot
- `data/ripplegate_demo_graph_v1.json`: 오류·보류 경로 재현용 합성 packet
- `data/ripplegate_pilot_packet_manifest_v1.json`: P01~P05 관찰 packet 정의
- `ripplegate_pilot_console.html` 및 paired 평가 도구: 실제 관찰 기록용 도구

## 재현

```powershell
python .\ripplegate_server.py --host 127.0.0.1 --port 8766
python .\ripplegate_http_smoke.py --base-url http://127.0.0.1:8766
python .\ripplegate_judge_repro.py --dataset public_snapshot
python .\ripplegate_judge_repro.py --holdout
python -m unittest discover -s . -p 'test_ripplegate.py'
```

기대 판정은 `VERIFIED 1 / SCENARIO 1 / HOLD 1`이며, 독립 Critic 결과와 HTTPS Evidence Ledger가 함께 출력된다.
`--holdout`은 10개 통제된 계약 mutation을 실행하며, 모두 `HOLD` 또는 `REJECT`여야 한다. 이 결과는 정확도나 실제 업무효과의 벤치마크가 아니다.

## 정직한 범위

이 패키지는 투자수익률 예측기나 자동 주문기가 아니다. 영향지수는 관찰값과 사람이 확인한 시나리오를 설명하기 위한 MVP 계산값이다. 공개 snapshot은 `REVIEW_REQUIRED`, 합성 packet은 `CONTROLLED_DEMO`로 취급하며, 미검증·기간 충돌 자료는 계산하지 않고 `HOLD`한다. P01~P05 업무효과는 실제 stopwatch·review log·trace·Evidence Ledger가 확보되기 전까지 주장하지 않는다.

