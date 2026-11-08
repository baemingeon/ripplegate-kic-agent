# RippleGate 보안 경계

이 문서는 공개 snapshot 기반 MVP의 보안 경계를 설명한다. MVP는 자동 매매·투자승인·리스크 한도 변경을 실행하지 않으며, 기관 운영 전환 시 별도 보안 검토가 필요하다.

## 위협과 통제

| 위협 | 현재 통제 | 실패 시 동작 |
|---|---|---|
| Prompt injection·악성 문서 | 알려진 지시 무시·프롬프트 공개·역할 전환·Tool 강제 패턴을 외부 gateway 호출 전에 격리; 사용자 목표·graph 필드는 untrusted data; Planner는 allowlist Tool만 제안; 숫자·가정·판정·주문 필드 거부 | 네트워크 호출 없이 결정론적 Planner fallback |
| 출처 위조·SSRF | 공개 출처는 HTTPS와 allowlist host만 허용; userinfo URL 거부; snapshot은 로컬 고정 | adapter validation 실패 |
| 미검증 숫자 확정 | `not_loaded` source를 사용하는 경로는 `HOLD`; 기준일·정의·단위 검사 | 숫자 계산 중단·REPLAN |
| XSS·UI 주입 | 서버 CSP·`nosniff`·`X-Frame-Options`; UI가 외부 문자열을 `esc()` 후 삽입 | 화면 표시만 실패하고 실행 권한 없음 |
| 요청 위조·과대 입력 | JSON object만 허용; Content-Type 검사; 128KB body 제한; 숫자 범위 제한 | 400/413으로 거부 |
| 잘못된 투자 자동화 | 사람 확인 전 계산 금지; 최종 판단은 사람; 거래·주문·한도 Tool 미제공 | `HUMAN_GATE` 대기 |

## LLM 경계

- 기본값은 LLM disabled이며 공개 snapshot과 결정론적 fallback만으로 재현한다.
- 승인된 private/OpenAI-compatible gateway를 연결할 때도 모델은 Tool 후보·위험 flag·질문만 반환한다.
- endpoint는 HTTPS(로컬 테스트는 loopback)만 허용하고, `KIC_LLM_ALLOWED_HOSTS`에 명시된 host가 아니면 네트워크 호출 전에 거부한다.
- 모델 출력은 허용된 최상위 필드, 허용 Tool, 배열 길이, 금지 필드를 검사한 뒤 정규화한다.
- 알려진 prompt injection marker가 사용자 목표 또는 graph 필드에서 발견되면 gateway를 호출하지 않고 `prompt_injection_suspected`를 기록한다. 이 탐지기는 완전한 공격 탐지기가 아니며, typed contract와 fallback이 최종 방어선이다.
- 숫자·가정·계산식·출처 ID·상태·의사결정·승인·거래·주문은 모델 출력에서 받지 않는다.
- API key는 환경변수로만 주입하며 응답·trace·검토팩에 기록하지 않는다.

## 운영 전환 조건

기관 내부 자료를 연결할 때는 SSO/OIDC, private model gateway, TLS, WAF, DLP, 비밀관리, 로그 접근통제, source별 라이선스·갱신주기·장애 fallback을 추가한다. 외부 모델로 내부 원문을 보내는 정책은 기관 승인을 먼저 받아야 한다.

## 재현 명령

```powershell
python .\test_ripplegate.py
python .\ripplegate_judge_repro.py --dataset public_snapshot
```

보안 관련 회귀 테스트는 Planner의 prompt injection 사전 격리, 금지 필드·미지 필드·Tool 과다 출력, 출처 URL의 userinfo·비 HTTPS·유사 도메인을 검사한다. 이 테스트는 운영 보안 인증을 대신하지 않는다.
