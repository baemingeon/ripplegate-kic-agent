# IC Preflight 본선 GitHub·Demo 제출 가이드 v0.3

목적: 본선 제출 직전에 필요한 공개 코드·Demo URL·선택 시연영상의 상태를 빠르게 확인한다. 이 문서는 코드를 새로 설명하는 문서가 아니라, 심사위원이 실제로 실행할 경로를 고정하는 체크리스트다.

## 심사위원에게 보여줄 최소 경로

1. Demo URL 접속
2. 화면에서 기본 재현 문장 확인
3. `대상 기업의 FY2025와 비교기업의 9M FY2026 실적을 비교해줘` 실행
4. `VERIFY fail → REPLAN → 원문 재조회 → HOLD` Trace와 보류 이유 확인
5. GitHub에서 README의 실행 명령과 `mvp/JUDGE_REPRO.md` 확인

첫 화면에서는 `IC Preflight`가 무엇을 하는지 한 문장으로 설명하고, Planner·Verifier·Evidence Ledger 같은 기술 용어는 상세 Trace를 열었을 때만 보이게 한다.

## GitHub 저장소에 넣을 것

- `mvp/` 코드와 `README.md`
- `mvp/JUDGE_REPRO.md`, `mvp/DEMO_RUNBOOK.md`
- `mvp/validate_release.py`, `mvp/validate_public_submission.py`
- `mvp/validate_effect_measurement.py`, `mvp/data/pilot_measurement_sheet_v0.2.json`
- `mvp/data/`의 공개자료 snapshot·benchmark·출처 정책·재현성 요약
- `mvp/assets/`의 UI 결과 이미지
- 외부자원 사용대장과 라이선스·출처 안내
- 팀이 실제로 배포한 버전과 일치하는 release ZIP 또는 그 안의 실행 파일

## GitHub에 넣지 않을 것

- API key, 비밀번호, 개인 연락처, 내부 문서, 비공개 투자자료
- `.env`, 로컬 모델 파일, 인증 토큰, 운영 로그에 남은 민감정보
- 확인하지 않은 KIC 내부 SOP·시간절감 수치·사고 사례

## 외부 링크가 생긴 뒤 실행할 명령

프로젝트 루트의 PowerShell에서 실행한다.

```powershell
$env:IC_PREFLIGHT_DEMO_URL = "https://실제-demo-url"
$env:IC_PREFLIGHT_GITHUB_URL = "https://github.com/실제-조직/실제-repository"
# 선택 영상이 업로드된 경우만 설정
# $env:IC_PREFLIGHT_VIDEO_URL = "https://youtu.be/실제-영상"
python .\mvp\validate_public_submission.py
```

`READY`가 나오면 Demo의 health·UI·API·재현 결과와 GitHub 응답을 확인한 것이다. 링크가 없을 때의 `READY_AFTER_LINKS`는 실패가 아니라, 외부 배포 전 상태를 숨기지 않는 대기 표시다. 링크가 설정됐는데 검증에 실패하면 `BLOCKED`로 보고 URL·서버 로그·실행 환경을 먼저 고친다.

## 제출 직전 대조

- 제품명: `IC Preflight (아이씨 프리플라이트)`
- 제출 PDF: 10페이지 이내
- 발표 PDF·GitHub·Demo URL·선택 영상이 같은 버전을 가리키는지 확인
- PPTX 표지의 팀명·팀장·팀원·연락처가 실제 정보인지 확인
- 발표에서는 “투자 승인 자동화”가 아니라 “투자심의 전 검증 packet 작성·보류”라고 설명
- 사람 stopwatch와 Agent end-to-end paired 측정이 P01~P05에 없으면 시간절감률을 발표하지 않음
