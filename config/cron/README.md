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

## 확인
```bash
hermes cron list            # 등록된 잡 목록
hermes cron run weather-0800  # 즉시 1회 실행(테스트)
```
