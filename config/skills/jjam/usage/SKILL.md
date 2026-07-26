---
name: usage
description: OpenAI 토큰 사용량과 예상 API 비용을 조회한다. "토큰 얼마 썼어", "이번 달 사용량", "OpenAI 비용", "/usage" 등을 물을 때 사용.
version: 1.0.0
author: jjam-agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [usage, cost, openai, tokens]
    category: jjam
    requires_toolsets: [terminal]
required_environment_variables:
  - name: ASSISTANT_DB
    prompt: 사용량 SQLite 경로
    help: 미설정 시 레포의 data/assistant.db. 보통 설정 불필요.
    required_for: 토큰 사용량 DB 위치 지정(선택)
---

# OpenAI 토큰 사용량 조회 (usage)

## When to Use
- 사용자가 토큰 사용량·OpenAI 예상 비용(오늘/이번 달)을 물을 때.
- `/usage`, `/usage today`, `/usage month` 명령.
- 기능별 분해를 원하면 `--feature`.

## Procedure
1. 저장소 루트(`terminal.cwd`)에서 사용량 요약 스크립트를 실행한다:
   ```bash
   python3 scripts/get-token-usage.py today            # 오늘(기본)
   python3 scripts/get-token-usage.py month            # 이번 달
   python3 scripts/get-token-usage.py today --feature   # 기능별 분해
   python3 scripts/get-token-usage.py month --json      # 기계용 JSON
   ```
   - 데이터는 `data/assistant.db`(SQLite)의 `token_usage` 테이블에서 KST 기준 집계된다.
2. 스크립트 출력(호출 수·입출력 토큰·예상 비용)을 사용자에게 그대로 전하거나 간결히 정리한다.

## Pitfalls
- **비용은 항상 "예상치"다.** 로컬 단가표(`usage_db.PRICING`) 기반이라 OpenAI 실제
  청구액과 다를 수 있음을 반드시 함께 알린다(무료 티어/할인/반올림/캐시 차이).
- `gpt-5.6-luna` 단가는 아직 공개 전이라 추정값이다. 실단가 확정 시 `usage_db.PRICING` 갱신.
- 기록이 없으면(초기/신규 설치) 0으로 표시된다 — 오류가 아니다.
- 이 스킬은 **조회 전용**이다. 사용량 기록(record_usage)은 실제 모델 호출부에서 적재한다.

## Verification
```bash
python3 scripts/get-token-usage.py --seed   # 더미 데이터 삽입(테스트용)
python3 scripts/get-token-usage.py today --feature
```
- 호출 수·토큰·"예상 비용(예상치…)" 라벨이 출력되면 정상.
