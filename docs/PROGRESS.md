# 진행 상황 (PROGRESS)

> 이 문서는 "어디까지 했고 무엇이 남았는지"를 기록한다. 작업이 진행되면 갱신한다.
> 최종 갱신: 2026-07-27 (PR #10 기준)

## 한 줄 요약
**코드·설정 레벨은 전부 완료.** 남은 것은 키 발급 + EC2 설치·배포(인프라)뿐.

---

## ✅ 완료 (코드/설정)

### 1. 도구 스크립트 (`scripts/`) — 전부 표준 라이브러리·단독 실행
- `get-weather.py` — 날씨 조회(`--json`/`--dry-run`/`--location`), 키 없으면 mock 폴백
- `collect-news.py` — **AI 중심 뉴스 수집**. sources.yml → RSS/GitHub릴리스/Brave → 최근 3일 필터 → 중복제거 → **이미 보낸 것 제외** → priority top-N(핵심 공식은 pinned)
- `sent_store.py` — 발송 항목 영구 기록(SQLite)으로 **날짜별 중복 발송 방지**
- `make-briefing.py` — 수집 → 카테고리 버킷(핵심AI/Java·Spring/기타) → OpenAI 요약(4섹션) → Discord Webhook 전송 → 발송기록
- `usage_db.py` + `get-token-usage.py` — OpenAI 토큰 사용량 기록·집계(SQLite), "예상 비용" 라벨
- `get-aws-cost.sh` — AWS 비용(month/services/forecast), 읽기전용 IAM Role 전제

### 2. Hermes 설정 (`config/`) — 공식 문서 스키마 검증됨
- `hermes.yaml` — 모델(gpt-5.6-luna)·terminal·memory·Discord 화이트리스트(gateway.platforms.discord.extra)
- `SOUL.md` — 에이전트 정체성(페르소나)
- `sources.yml` — 뉴스 소스 29개(객체 리스트: id/name/type/category/url/priority)
- `cron/README.md` — 예약 작업 등록 명령(08시 날씨 / 09시 브리핑 / 월간 프루닝)
- `prompts/{weather,daily-briefing}.md` — 요약 프롬프트(daily-briefing 은 4섹션 구조)

### 3. Hermes 스킬 (`config/skills/jjam/`)
- `weather` · `briefing` · `usage` · `cost` — 각 `SKILL.md`(실제 Hermes 스킬 스키마)

### 4. 뉴스 브리핑 파이프라인 (사용자 지정 흐름 그대로)
```
매일 09:00 → sources.yml → RSS/GitHub/Brave 수집 → 최근 3일 필터 → 중복제거
→ 이미 보낸 것 제외 → priority top8(핵심 공식 pinned) → 카테고리 버킷
→ OpenAI 요약(핵심AI/Java·Spring/기타/아이디어) → Discord Webhook → 발송기록
```

### PR 이력 (모두 머지됨)
| PR | 내용 |
|----|------|
| #1 | 스캐폴드(도구·config·프롬프트·에이전트 정의) |
| #2 | Hermes 실제 문서 스키마로 config 교정(SOUL.md, gateway 실필드, memory) |
| #3 | 날씨 스킬 + 08시 cron |
| #4 | 뉴스 브리핑 스킬 + 09시 cron |
| #5 | `/usage`·`/cost` 스킬 |
| #6 | README 상태 갱신 |
| #7 | AI 중심 뉴스 수집 파이프라인 재설계(sources.yml·3일·pinned·top-N) |
| #8 | 이미 보낸 항목 제외(sent_store, 중복 발송 방지) |
| #9 | make-briefing.py(카테고리 브리핑 생성·전송) |
| #10 | 진행 기록(PROGRESS.md) + README 갱신 |

---

## ⏳ 남은 것 (인프라 — 실제 설치·배포)

절차 상세: [`SETUP_HERMES.md`](SETUP_HERMES.md)

1. **키 발급·설정** (사용자)
   - `OPENAI_API_KEY` (필수) — 브리핑 요약·대화
   - `DISCORD_BOT_TOKEN` + 본인 `DISCORD_ALLOWED_USER_ID` — 게이트웨이 대화
   - `DISCORD_WEBHOOK_URL` — 브리핑 자동 전송
   - `WEATHER_API_KEY` (선택, 없으면 mock)
   - `BRAVE_API_KEY` (선택, 없으면 RSS 19개만 수집)
2. **EC2 준비** — t3.micro/Ubuntu, Swap 2GB, TZ=Asia/Seoul, 읽기전용 IAM Role(비용 조회)
3. **Hermes 설치·연결** — install → `hermes config set` 키 저장 → `hermes model`(Luna 확인)
4. **게이트웨이 기동** — `hermes gateway` → Discord 왕복 확인
5. **cron 등록** — `hermes cron create` 로 08/09시 잡 + 월간 프루닝
6. **상시 운영** — `hermes gateway install` + `loginctl enable-linger`(재부팅 자동 실행)
7. **검증** — 재부팅 후 자동 복구, 7일 안정 실행

---

## 📝 참고 결정·메모
- **런타임 = Hermes 확정**(자체 봇 아님). 브리핑 파이프라인은 자체 완결 스크립트라 Hermes cron(no-agent/script)이 실행만 담당.
- **뉴스 = AI 중심**. 핵심 공식 발표(OpenAI·Anthropic 등 priority 10)는 3일 내 나오면 top 제한 무관 항상 포함.
- **Brave API 비용**: 우리 사용량 ≈ 월 300회 → $5 무료 크레딧 내(실질 무료). 단 신규 가입은 카드 등록 필요. 급하지 않으면 RSS 19개로 먼저 운영 가능.
- **브리핑 top 기본값 8** (카테고리 3분할 고려). `make-briefing.py --top N` 으로 조정.
