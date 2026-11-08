# GitHub·Demo 제출 체크리스트

## 저장소

- 저장소 root에서 `README.md`를 먼저 읽는다.
- `python .\mvp\server.py`로 UI를 실행한다.
- `python .\mvp\test_mvp.py`가 통과하는지 확인한다.
- `mvp/JUDGE_REPRO.md`의 한 문장 재현을 수행한다.
- `.gitignore`로 team_info, API key, 모델 실행 로그, build 산출물을 제외한다.

## 공개 Demo

- `/health`가 `status=ok`, `service=IC Preflight`를 반환한다.
- UI에서 `IC Preflight`와 모델 없는 안전 확인이 보인다.
- 재현 문장에서 기간 불일치 후 `HOLD`가 표시된다.
- 감사 로그 다운로드와 원문 근거 링크를 확인한다.
- 모델이 없거나 timeout이어도 결정론적 경로가 끝까지 실행된다.

## 제출 전 환경변수

```powershell
$env:IC_PREFLIGHT_DEMO_URL = "https://실제-demo-url"
$env:IC_PREFLIGHT_GITHUB_URL = "https://github.com/실제-저장소"
# 선택 영상
# $env:IC_PREFLIGHT_VIDEO_URL = "https://youtu.be/실제-영상"
python .\mvp\validate_public_submission.py
```

`READY_AFTER_LINKS`는 링크가 없는 상태이며, 링크가 설정됐는데 실패하면 `BLOCKED`로 간주한다. 실제 링크와 팀 정보는 사용자가 제공한 뒤에만 최종 제출물에 주입한다.
