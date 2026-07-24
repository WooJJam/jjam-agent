# Hermes 기반 개인 AI 비서(POC) — 개발 오케스트레이션 & 구현 계획

## Context (왜 이 계획인가)

`jjam-agent`는 아직 **빈 디렉터리 + git 미초기화** 상태의 그린필드 프로젝트다. 목표는
Discord로 쓰는 개인 AI 비서 POC(뉴스 브리핑 / 날씨 / OpenAI 사용량 / AWS 비용 / 일반 대화)를
**Hermes 런타임** 위에 구성해 EC2 t3.micro에 배포하는 것이다.

이 문서는 "무엇을 만들까"가 아니라 **"내(Claude Code)가 이걸 어떤 에이전트/스킬 구성으로,
github-flow로 어떻게 만들어 나갈까"** 를 정의한다. 사용자의 질문:
필요한 에이전트 수·역할, 각 에이전트 호출 방식, 필요한 skills, 그리고 전체 구현 계획.

### 확정된 환경 (실측)
- git 2.55 ✅ / Node v24 ✅ / Python 3.12.10 (`py` 런처) ✅ / npm 11 ✅
- **`gh` CLI 미설치** ❌ / **git repo 미초기화** ❌ / Hermes 미설치 ❌
- Hermes = NousResearch 오픈소스 에이전트 런타임(2026-02): CLI + Discord 게이트웨이 +
  cron 스케줄러 + 마크다운 메모리(`~/.hermes/`) + 서브에이전트 + skills(플러그인) 내장.
  → 즉 이 POC의 대부분은 "코드"보다 **Hermes 설정(config/prompts/skills/scripts/cron)** 작성이다.

### 확정 사항 (사용자 지정)
- **원격 레포**: `https://github.com/WooJJam/jjam-agent.git` (이미 생성됨).
- **시크릿**: 모든 비밀값은 `.env`에만 보관, **절대 GitHub에 커밋/푸시 금지**. `.gitignore`로 `.env` 차단, `.env.example`만 커밋.
- **즉시 작업**: 다른 데스크탑에서 이어서 작업할 수 있도록 **실행계획 문서를 먼저 레포에 푸시**한다(아래 P0 참고).

### 전제 (사용자 미응답 항목 — 변경 가능)
1. **에이전트 구성**: `.claude/agents/`에 **전용 서브에이전트 정의 파일**을 만들어 반복 호출·권한 명확화.
2. **런타임**: 계획대로 **Hermes 사용**. 단 신생 런타임 리스크 대비, 각 도구(scripts)는 Hermes 비의존 단독 실행 가능하게 설계(자체 Python 봇으로 폴백 가능).

---

## 1. 개발 방법론 개요

두 개의 "에이전트 레이어"를 구분한다.

| 레이어 | 정체 | 산출물 |
|--------|------|--------|
| **빌드 레이어 (나)** | Claude Code + 내가 띄우는 서브에이전트 | repo 코드/설정, PR, 리뷰 |
| **런타임 레이어 (제품)** | EC2 위 Hermes + skills/scripts/cron | 실제 동작하는 비서 |

github-flow: `main` 보호 → 기능별 **feature 브랜치** → PR → **서브에이전트 셀프 리뷰** → 머지.
Phase 하나 = 브랜치 하나 = PR 하나를 기본 단위로 한다.

---

## 2. 빌드 레이어 — 서브에이전트 로스터 (몇 개 / 역할 / 호출법)

핵심 **전용 서브에이전트 5종** + 내장 유틸 에이전트 2종을 사용한다.
전용 에이전트는 `.claude/agents/*.md`(frontmatter: name/description/tools/model)로 정의해 재사용한다.

### 2.1 전용 서브에이전트 (`.claude/agents/`)

| # | 에이전트(name) | 역할 | 주 담당 Phase | 호출 방식 |
|---|----------------|------|---------------|-----------|
| A1 | `news-briefing-dev` | RSS/검색 수집·24h 필터·중복제거·요약 프롬프트(collect-news.py, daily-briefing.md) | Phase 4 | `Agent(subagent_type:"news-briefing-dev")` |
| A2 | `weather-dev` | 날씨 API 연동·get-weather.py·weather.md·기본지역 서울(env로 변경 가능) | Phase 3 | 〃 |
| A3 | `cost-usage-dev` | OpenAI 토큰 기록(SQLite)·get-token-usage.py·AWS Cost Explorer(get-aws-cost.sh)·`/usage` `/cost` | Phase 5 | 〃 |
| A4 | `hermes-integration-dev` | Hermes 설치/설정·Discord 게이트웨이·화이트리스트·cron 등록·systemd·prompts/system.md | Phase 1·2·6 | 〃 |
| A5 | `reviewer` | PR 셀프 리뷰 전용(정확성·보안·비밀노출·에러처리). code-review 스킬 래핑 | 전 Phase(머지 전) | 〃, PR마다 |

### 2.2 내장 에이전트 (정의 불필요, 즉석 호출)
- **Explore**: 신규 코드/설정 패턴·라이브러리 조사(예: discord.py vs Hermes 게이트웨이 옵션). 불확실 구간 착수 전.
- **Plan**: 도메인 설계가 복잡할 때(예: 뉴스 파이프라인 스키마, 토큰비용 계산 테이블) 착수 전 1회.

### 2.3 호출 원칙
- **병렬화**: 서로 의존 없는 도메인(날씨/뉴스/비용)은 한 메시지에서 `Agent` 다중 호출로 동시 진행.
- **컨텍스트 이어가기**: 같은 도메인 후속 작업은 새 `Agent`가 아니라 `SendMessage`로 기존 에이전트에 이어붙여 문맥 보존.
- **리뷰 분리**: 구현 에이전트와 `reviewer`를 반드시 분리(자기 코드 자기검증 편향 방지). PR 올리기 전 `reviewer` 통과 필수.
- **격리**: 병렬로 파일을 동시 수정해 충돌 우려 시에만 `isolation:"worktree"` 사용(비용 큼, 남용 금지).

---

## 3. 사용할 Skills

| Skill | 용도 | 시점 |
|-------|------|------|
| `/code-review` (필요 시 `ultra`) | PR 머지 전 브랜치 리뷰. `reviewer` 에이전트 또는 내가 직접 실행 | 각 PR |
| `artifact-design` | 최종 운영 문서/체크리스트를 보기 좋은 아티팩트로 낼 경우 | Phase 6(선택) |
| (Hermes skills) | **런타임 산출물** — Hermes가 auto-write하거나 우리가 작성하는 briefing/weather/cost skill. 빌드 스킬 아님 | Phase 3~5 |

> `/code-review ultra`는 사용자만 트리거 가능(과금). 나는 `reviewer` 서브에이전트 + 일반 `/code-review`로 셀프 리뷰한다.

---

## 4. github-flow 세부

### 브랜치 전략
- `main` (보호, 항상 배포가능)
- `feat/phase1-hermes-bootstrap`, `feat/phase2-discord`, `feat/phase3-weather`,
  `feat/phase4-briefing`, `feat/phase5-cost-usage`, `feat/phase6-deploy`
- 브랜치명 규칙: `feat/…`, `fix/…`, `docs/…`, `chore/…`

### 커밋
- 논리 단위 커밋, 메시지 끝에 Co-Authored-By 트레일러 포함.
- 비밀값 커밋 금지: 착수 즉시 `.gitignore`(`.env`, `data/*.db`, `logs/`, `__pycache__/`, `.hermes/`) + `.env.example`만 커밋.

### PR & 리뷰 루프 (Phase마다)
1. `git switch -c feat/phaseN-…`
2. 해당 도메인 에이전트가 구현 → 커밋
3. `reviewer` 에이전트 리뷰 → 지적사항 수정 커밋
4. `git push -u origin …`
5. `gh pr create` (제목/본문/체크리스트, 🤖 Generated 트레일러)
6. PR 코멘트로 리뷰 요약 → 필요 시 추가 커밋 → `gh pr merge --squash`
7. `main` 갱신 후 다음 Phase 브랜치 분기

### 선행 작업 (사용자)
- GitHub 인증 1회(HTTPS 자격증명 or `gh auth login`). 이후 푸시/PR은 내가 수행.
- 계정 발급류(AWS/OpenAI/Discord/날씨 키)는 POC 기획서 7절대로 사용자 담당.

---

## 5. 런타임 레이어 산출물 (디렉터리)

POC 기획서 5절 구조를 그대로 구현하되, 각 script는 **CLI 단독 실행 + Hermes skill에서 호출** 양쪽 지원.

```
jjam-agent/                       # repo 루트
├── config/ hermes.yaml, sources.yaml, prompts/{system,daily-briefing,weather}.md
├── scripts/ collect-news.py, get-weather.py, get-aws-cost.sh, get-token-usage.py
├── data/ assistant.db, cache/
├── logs/
├── systemd/ hermes-assistant.service
├── docs/ DEVELOPMENT_PLAN.md, POC_SPEC.md
├── .env.example, .gitignore, README.md
└── .claude/agents/*.md           # 빌드 레이어 에이전트 정의(레포에 함께 버전관리)
```

---

## 6. 단계별 구현 계획 (Phase = 브랜치 = PR)

각 Phase는 POC 기획서 8절 완료 기준을 그대로 승계한다.

- **P0 부트스트랩(완료)** `main`:
  git init → remote `origin = WooJJam/jjam-agent` 연결 →
  `.gitignore`(`.env`/`data/*.db`/`logs/`/`__pycache__/`/`.hermes/`) + `.env.example` + `README.md` +
  **실행계획 문서 `docs/DEVELOPMENT_PLAN.md`(이 문서) & `docs/POC_SPEC.md`(원본 기획)** →
  커밋 → **push (다른 데스크탑 이어작업용)**. 시크릿 미포함 검증 후에만 push.
- **P1 로컬 최소기능** `feat/phase1-hermes-bootstrap`: Hermes 설치·GPT-5.6 Luna 연결·터미널 대화·토큰기록 스텁. (A4, Explore 선조사)
- **P2 Discord** `feat/phase2-discord`: 게이트웨이 연결·사용자/채널 화이트리스트·송수신. (A4)
- **P3 날씨** `feat/phase3-weather`: get-weather.py·`/weather`·08시 cron. (A2) — P4와 **병렬 가능**
- **P4 브리핑** `feat/phase4-briefing`: sources.yaml·collect-news.py·24h/중복필터·Luna 요약·`/briefing`·09시 cron. (A1, Plan 선설계)
- **P5 비용/사용량** `feat/phase5-cost-usage`: 토큰 SQLite 스키마·get-token-usage.py·get-aws-cost.sh·`/usage` `/cost`. (A3)
- **P6 배포/안정화** `feat/phase6-deploy`: EC2 설치·Swap·systemd·logrotate·재부팅복구·모니터링·운영문서. (A4)

의존: P0→P1→P2 순차, P2 이후 **P3·P4·P5 병렬 착수 가능**, 전부 머지 후 P6.

---

## 7. 검증 방법 (End-to-End)

- **도구 단위**: 각 script를 로컬에서 `py scripts/get-weather.py` 등으로 단독 실행해 JSON/텍스트 출력 확인.
- **Discord 왕복**: 화이트리스트 사용자로 메시지 → Hermes 응답 확인(P2 완료 기준).
- **스케줄**: cron 시각을 임시로 앞당겨 08/09시 브리핑·날씨 자동 전송 확인 후 원복.
- **비용/사용량**: 더미 호출 기록 후 `/usage today`, `/cost month` 출력 검증. 로컬은 "예상 비용" 라벨.
- **배포**: EC2 재부팅 후 `systemctl status hermes-assistant` 자동 실행 + 7일 안정성 모니터링(기획서 9절).
- **보안 게이트(머지 전 필수)**: 비밀값 미커밋, 로그 내 키 미출력, IAM Role(액세스키 X), Discord 화이트리스트를 `reviewer`가 매 PR 확인.

---

## 8. 열린 질문 (사용자 확인 필요)
1. `.claude/agents/` 전용 에이전트 파일 생성에 동의하는지(레포에 함께 커밋됨).
2. 런타임을 Hermes로 확정할지, 안정성 우선 자체 Python 봇으로 갈지.
3. GitHub 인증 방식(HTTPS 자격증명 캐시 vs `gh auth login`).
