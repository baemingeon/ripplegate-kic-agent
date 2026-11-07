# RippleGate P01~P05 paired 측정

이 프로토콜은 효과를 미리 주장하기 위한 문서가 아니다. 현재 RippleGate packet 정의는 `data/ripplegate_pilot_packet_manifest_v1.json`을 기준으로 하며, 동일한 입력 packet에 대해 사람이 평소 방식으로 만든 결과와 RippleGate를 사람이 직접 관찰한 결과를 같은 범위로 기록하기 위한 장치다.

## 기록 규칙

- `P01`~`P05`는 서로 다른 사람이 아니라 동일 업무 유형의 5개 입력 packet ID다.
- 수작업과 Agent 모두 입력 수령부터 검토 가능한 결과까지의 end-to-end 시간을 기록한다.
- 수작업에는 stopwatch와 review log 참조가 필요하다.
- Agent에는 run trace와 Evidence Ledger 참조가 필요하다.
- 실제 로그를 확인하지 않은 숫자는 기록하지 않는다. 기록기는 `--observed-by-human` 없이는 실행되지 않는다.
- P01~P05가 모두 manual·agent 한 쌍을 갖기 전에는 시간 절감률을 발표자료에 넣지 않는다.
- 자동 브라우저 harness 결과(`ripplegate_agent_runtime_p01_p05_20261108.json`)는 Agent 측 실행 증거일 뿐, 사람 수작업 시간·paired 효과 측정으로 집계하지 않는다.

## 기록 명령

브라우저에서 빠르게 입력하려면 `ripplegate_pilot_console.html`을 열어 P01~P05의 수작업 stopwatch와 review log를 기록한다. Agent 참고값은 자동 harness 결과를 보여주지만, 품질 필드와 최종 paired 기록은 실제 확인 후 확정한다.

콘솔 export를 확인한 뒤에는 `python .\record_paired_console_export.py --input <export.json> --observed-by-human`으로 guarded paired log에 넣는다.

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
