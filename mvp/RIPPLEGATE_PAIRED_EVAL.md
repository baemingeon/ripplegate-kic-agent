# RippleGate P01~P05 paired 측정

이 프로토콜은 효과를 미리 주장하기 위한 문서가 아니다. 현재 RippleGate packet 정의는 `data/ripplegate_pilot_packet_manifest_v1.json`을 기준으로 하며, 동일한 입력 packet에 대해 사람이 평소 방식으로 만든 결과와 RippleGate를 사람이 직접 관찰한 결과를 같은 범위로 기록하기 위한 장치다.

## 기록 규칙

- `P01`~`P05`는 서로 다른 사람이 아니라 동일 업무 유형의 5개 입력 packet ID다.
- 수작업과 Agent 모두 입력 수령부터 검토 가능한 결과까지의 end-to-end 시간을 기록한다.
- 수작업에는 stopwatch와 review log 참조가 필요하다.
- Agent에는 run trace와 Evidence Ledger 참조가 필요하다.
- 실제 로그를 확인하지 않은 숫자는 기록하지 않는다. 기록기는 `--observed-by-human` 없이는 실행되지 않는다.
- canonical 기록 파일은 `paired_eval_log.jsonl`이며, 각 packet은 `condition=manual`과 `condition=agent` 두 줄을 모두 가져야 한다. 두 조건 모두 `timing_scope=end_to_end_workflow`, 실제 관찰시간, 익명 operator ID와 해당 검토 증거를 가져야 제출 검수가 열린 게이트를 닫는다.
- P01~P05가 모두 manual·agent 한 쌍을 갖기 전에는 시간 절감률을 발표자료에 넣지 않는다.
- 자동 브라우저 harness 결과(`ripplegate_agent_runtime_p01_p05_20261108.json`)는 Agent 측 실행 증거일 뿐, 사람 수작업 시간·paired 효과 측정으로 집계하지 않는다.

## 측정 편향 통제

- 각 packet은 동일한 입력 문장·자료 범위·완료 정의로 수행하고, packet manifest 버전과 실행 순서를 review log에 남긴다.
- 학습효과를 줄이기 위해 일부 packet은 수작업부터, 일부 packet은 Agent부터 시작한다. 순서를 섞지 못하면 그 사실을 결과와 함께 공개한다.
- 수작업 수행 중 Agent 결과를 참고하지 않고, Agent 수행 중 수작업 결과를 복사하지 않는다.
- 측정 시간은 입력 수령부터 검토 가능한 결과·다음 행동이 남는 시점까지의 end-to-end 시간이다. 서버 runtime·네트워크 latency만으로 업무시간 절감률을 계산하지 않는다.
- 판단 결과·source gap·재작업·계산 불일치의 판정 기준을 측정 전에 고정하고, 한 packet만 유리하게 선택해 보고하지 않는다.

## 기록 명령

브라우저에서 빠르게 입력하려면 `ripplegate_pilot_console.html`을 열어 P01~P05마다 수작업 stopwatch와 Agent end-to-end stopwatch를 각각 실행하고 review log·trace·Evidence Ledger를 기록한다. Agent 참고값은 자동 harness 결과로 표시될 뿐 입력값으로 복사되지 않으며, 품질 필드와 최종 paired 기록은 실제 확인 후 확정한다.

콘솔 export를 확인한 뒤에는 `python .\record_paired_console_export.py --input <export.json> --observed-by-human`으로 guarded paired log에 넣는다.

현재 canonical 검증기는 `python .\validate_ripplegate_paired.py --strict`이다. 이 검증기는 `data/ripplegate_pilot_packet_manifest_v1.json`과 export의 dataset·목표·예상 판정을 대조하고, 자동 브라우저 runtime-only 기록을 사람 paired 측정으로 승격하지 않는다.

```powershell
python .\ripplegate_paired_eval.py --packet-id P01 `
  --operator-id op-anon-01 `
  --review-log-reference .\pilot_logs\P01-review.log `
  --agent-trace-reference trace:P01-agent-01 `
  --evidence-ledger-reference ledger:P01-agent-01 `
  --manual-minutes <실제 수작업 분> --agent-minutes <실제 Agent 분> `
  --manual-rework-count <실제 회> --agent-rework-count <실제 회> `
  --manual-source-gaps <실제 건> --agent-source-gaps <실제 건> `
  --manual-calculation-inconsistencies <실제 건> --agent-calculation-inconsistencies <실제 건> `
  --manual-decision REVIEW --agent-decision REVIEW `
  --observed-by-human
```

기본 출력은 `AWAITING_HUMAN_PAIRING`, 일부 packet만 완료하면 `INCOMPLETE`, 다섯 packet 모두 두 조건을 갖추면 `READY_TO_REPORT`다. `READY_TO_REPORT`는 표본 5개의 파일럿 측정 준비가 끝났다는 뜻이며, 기관 전체 업무효과나 수상 가능성을 보장하지 않는다.
