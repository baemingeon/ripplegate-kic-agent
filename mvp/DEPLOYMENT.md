# Public demo deployment

본선 제출용 Demo URL을 만들 때 사용하는 배포 경로입니다. 공개 demo는 공개자료 snapshot과 합성 오류 케이스만 제공하며 내부 문서·API key·개인정보를 포함하지 않습니다.

## Docker

`mvp` 폴더를 Docker context로 사용합니다.

```powershell
docker build -t ic-preflight-demo .
docker run --rm -p 8765:8765 -e KIC_HOST=0.0.0.0 -e PORT=8765 ic-preflight-demo
```

확인:

```text
http://localhost:8765/health
```

응답은 `status=ok`, `service=IC Preflight`, `mode=public_demo_snapshot`을 반환해야 합니다.

## 실행 프로파일과 PC 사양

- 현재 개발 PC 프로파일(i5-12400F·16GB RAM·RTX 3050 4GB)에서는 `모델 없이 안전 게이트 실행`을 기본으로 사용합니다. 자료 snapshot·typed Controller·Decimal 계산·UI는 GPU 없이 동작합니다.
- 특정 모델은 이 PC의 운영 기본 모델이 아닙니다. 공개 Demo의 필수 조건은 모델 없는 안전 게이트입니다.
- LLM이 필요할 때는 승인된 private/OpenAI-compatible gateway만 선택 연결하되, `KIC_LLM_POLICY=approved`와 provider/model allowlist를 먼저 통과시킵니다.
- 모델 호출 실패·timeout·JSON 오류가 나면 Planner/Reflection 제안만 fallback하고, 계산·출처·HOLD 판정은 결정론적 경로를 유지합니다.

## Render

저장소 root에서 `render.yaml`을 읽도록 연결하거나, Docker service의 context를 `mvp`로 지정합니다. health check는 `/health`로 설정합니다. 승인 LLM이 없는 공개 demo에서도 모델 없는 안전 게이트와 투자심의팩이 끝까지 실행됩니다.

## 운영 전환 전 필수 조치

- 공개 demo와 KIC 내부환경을 분리하고 인증·접근권한·로그 보존정책을 적용한다.
- Yahoo snapshot adapter를 승인된 vendor·거래소 market-data feed로 교체하고 라이선스를 확인한다.
- SEC 요청은 실제 담당 연락처를 `KIC_SEC_CONTACT`로 설정하고 User-Agent·fair-access 조건을 준수한다.
- 내부 문서 사용 시 private endpoint 또는 승인된 사내 모델을 사용한다.
- 모델 연결은 보안 승인을 받은 `openai_compatible` private gateway만 허용하고, `KIC_LLM_API_KEY`는 secret store에서 주입한다. 특정 모델·provider는 기본 경로가 아니며 allowlist와 보안 승인 후에만 선택한다.
