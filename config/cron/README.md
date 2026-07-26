# 예약 작업 (Hermes cron)

Hermes cron 잡은 `~/.hermes/cron/jobs.json` 에 저장된다. **직접 편집은 권장되지 않으며**,
`hermes cron` CLI(또는 대화 중 cronjob 도구)로 관리한다. 이 문서는 jjam-agent 가 등록할
잡을 선언적으로 기록한 것으로, 배포 시 아래 명령으로 등록한다.

> 필드 근거: <https://hermes-agent.nousresearch.com/docs/user-guide/features/cron>
> 핵심 필드 — `schedule`(cron 식), `skill`, `deliver`("discord:#채널"), `prompt`, `no_agent`, `script`.
> 스케줄은 시스템 타임존(EC2 `TZ=Asia/Seoul`) 기준으로 해석된다.
> `#daily` 는 예시 채널명이다. 실제 채널명으로 바꿔 등록한다.

## 등록된 잡

### weather-0800 — 매일 오전 8시 날씨 브리핑
```bash
hermes cron create \
  --name weather-0800 \
  --schedule "0 8 * * *" \
  --skill weather \
  --deliver "discord:#daily"
```
- `weather` 스킬이 `scripts/get-weather.py --json` 을 실행 → `config/prompts/weather.md`
  형식으로 요약 → 지정 채널로 전송.

### briefing-0900 — 매일 오전 9시 AI·개발 뉴스 브리핑
```bash
hermes cron create \
  --name briefing-0900 \
  --schedule "0 9 * * *" \
  --no-agent \
  --script "scripts/make-briefing.py"
```
- `make-briefing.py` 가 전 과정을 스스로 수행하므로 **agent/deliver 불필요**(no-agent 스크립트 잡):
  `collect-news.py`(최근 3일·중복제거·**이미 보낸 것 제외**·priority top8, 핵심 공식은 항상 포함)
  → 카테고리 버킷(핵심 AI/Java·Spring/기타) → OpenAI 요약(`daily-briefing.md` 형식)
  → **Discord Webhook 전송**(`DISCORD_WEBHOOK_URL`) → `sent_store.mark_sent`(중복 발송 방지).
- 전송은 게이트웨이가 아니라 **Webhook** 을 쓰므로 `DISCORD_WEBHOOK_URL` 를 `hermes config set` 로 저장.

### 저장소 정리(선택) — 발송기록 프루닝
```bash
hermes cron create \
  --name sent-prune \
  --schedule "0 4 1 * *" \
  --no-agent \
  --script "scripts/sent_store.py prune --days 30"
```
- 월 1회 30일 지난 발송기록 삭제(DB 비대화 방지).

## 확인
```bash
hermes cron list            # 등록된 잡 목록
hermes cron run weather-0800  # 즉시 1회 실행(테스트)
```
