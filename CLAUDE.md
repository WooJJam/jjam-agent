# jjam-agent 작업 규칙 (CLAUDE.md)

Hermes 기반 Discord 개인 AI 비서 POC. 아래 규칙은 이 레포의 모든 Claude Code 세션에
적용된다.

## 1. 모든 작업은 이슈에서 시작한다

- 새 작업 착수는 `/open-issue` 스킬로: 이슈 생성(템플릿 준수) → `<타입>/<이슈번호>-<슬러그>`
  브랜치 체크아웃. 이슈 없는 작업 브랜치 금지 (예외는 사용자의 명시 지시뿐)
- 타입: `feat | fix | docs | infra | chore`, 라벨은 사전 정의 11종만(타입 5 + 도메인 6)

## 2. main 직접 커밋 금지

- 항상 브랜치에서 작업하고 PR로 합친다. main 직접 push 금지
- 브랜치는 항상 최신 `origin/main` 기준으로 분기

## 3. PR·머지·원격 변형은 사용자 명시 요청 시에만

- PR 생성은 `/open-pr` 스킬로만 — 승인 게이트 통과 전에는 push·PR 생성 금지
- 머지, 이슈/라벨 생성·삭제, 브랜치 삭제 등 원격 변형은 사용자가 그 행위를
  콕 집어 지시했을 때만 실행. "만들어줘/작성해줘"는 로컬 파일 초안까지만
- 플랜 모드 중에는 계획서 작성만 — 파일 생성·커밋·원격 변형 금지

## 4. 커밋 컨벤션

- 메시지: `타입(스코프): 요약 (#이슈번호)` — 본문은 논리 단위 설명
- 끝에 `Co-Authored-By: Claude ...` 트레일러 유지
- PreToolUse 훅(secret_scan --pretool)이 `git commit` 시 스테이징 diff의 시크릿·
  금지파일을 검사해 차단한다. 이 검사를 우회하는 커밋 방법을 쓰지 않는다

## 5. 시크릿·개인 데이터 취급 금지 (최우선)

**무조건 차단 3경로**: ① 시크릿의 대화 컨텍스트 유입 ② 시크릿의 커밋/깃허브 유입
③ Claude의 시크릿·실데이터 파일 직접 수정. 그 외 위험 명령(force push 등)은
차단이 아니라 **무조건 확인(ask)** 레벨이다. 하네스가 강제한다:

- **읽기 금지**: `.env*`(.env.example 제외), `data/`, `*.xlsx`, `*.db`,
  `~/.hermes/.env`는 Read·cat·Get-Content 전부 deny — 값이 컨텍스트에 들어올 수 없다.
  우회 시도 금지
- **입력 차단**: 사용자 입력의 시크릿 패턴은 UserPromptSubmit 훅(secret_scan --prompt)이
  모델 전송 전에 차단한다. 시크릿 입력이 필요한 작업은 사용자가 터미널에서 직접
  (`hermes config set KEY VALUE`, `.env` 직접 편집) — Claude는 값 없이 절차만 안내
- **커밋 차단**: `git commit`은 PreToolUse 훅이 스테이징 diff를 스캔한 뒤에만 실행됨
- **직접 수정 금지**: `.env`·`data/`·xlsx·db는 Edit/Write deny — 값 기록·갱신은
  전부 스크립트 실행 또는 사용자 직접
- **위험 명령은 ask**: force push·reset --hard는 복합 명령 속에 있어도 훅이
  검출해 무조건 확인을 띄운다 (차단 아님 — 승인하면 실행됨)
- API 키·토큰을 코드·이슈·PR·응답·로그에 절대 출력하지 않는다
- 테스트·예시는 더미 데이터만 (플레이스홀더는 `xxxx` 형태 — 스캐너가 예외 처리함)

## 6. 코드 원칙

- Python은 `py` 런처로 실행, 표준 라이브러리 원칙(명시된 예외: openpyxl, discord.py)
- KST는 `timezone(timedelta(hours=9))` 고정 오프셋
- 스크립트는 Hermes 비의존 CLI 단독 실행 가능하게 설계
- `.py` 저장 시 PostToolUse 훅이 py_compile 검증 — 오류는 즉시 수정
- `terraform apply/destroy`는 Claude 실행 금지(deny) — plan까지만, apply는 사용자

## 참고 문서

- 진행 상황: docs/PROGRESS.md / 개발 계획: docs/DEVELOPMENT_PLAN.md
- 자산 관리 스펙: docs/FINANCE_SPEC.md (뱅크샐러드 포맷 기준)
- Hermes 설치·운영: docs/SETUP_HERMES.md
