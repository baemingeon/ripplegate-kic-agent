# r13 공개 데이터 범위

| 파일 | 용도 | 상태 |
|---|---|---|
| `ripplegate_public_graph_v1.json` | UNCTAD·EIA 관찰값과 UN Comtrade query reference를 연결한 기본 시연 | 공개자료, 운영 feed 아님; Comtrade 원시 응답값 미포함 |
| `ripplegate_demo_graph_v1.json` | 기간 충돌·자료 누락 등 HOLD 경로 재현 | 합성 packet |
| `ripplegate_pilot_packet_manifest_v1.json` | 동일 입력 paired 관찰용 P01~P05 packet 정의 | 측정 템플릿 |

자료가 없거나 기준일·단위·정의가 맞지 않는 경로는 값을 추정해 채우지 않고 `REQUEST_INFO` 또는 `HOLD`로 남긴다.
