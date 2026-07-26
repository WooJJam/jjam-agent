---
name: briefing
description: 최근 24시간 AI·개발 뉴스를 수집·요약해 데일리 브리핑으로 전달한다. "뉴스", "오늘 소식", "브리핑", "자바/스프링 업데이트" 등을 물을 때, 그리고 매일 오전 9시 자동 브리핑에 사용.
version: 1.0.0
author: jjam-agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [news, briefing, daily, dev]
    category: jjam
    requires_toolsets: [terminal]
---

# AI·개발 데일리 브리핑 (briefing)

## When to Use
- 사용자가 대화 중 오늘/최근 개발 뉴스, AI·IT·Java·Spring·인프라 소식을 **즉석으로** 물을 때.
- (자동 09시 브리핑은 이 스킬이 아니라 cron 의 `make-briefing.py` 잡이 담당한다.)

## Procedure
즉석 요청은 브리핑 파이프라인을 **전송 없이** 실행해 결과만 보여준다:
```bash
python3 scripts/make-briefing.py --no-send            # 수집→버킷→OpenAI 요약, 콘솔 출력(전송·기록 없음)
python3 scripts/make-briefing.py --no-send --top 10   # 더 많이 보고 싶을 때
```
- 내부적으로 `collect-news.py`(최근 3일·중복제거·**이미 보낸 것 제외**·priority top, 핵심 공식은 항상 포함)
  → 카테고리 버킷(핵심 AI/Java·Spring/기타) → `config/prompts/daily-briefing.md` 4섹션 요약.
- `--no-send` 라 **발송기록(sent_store)을 건드리지 않는다** — 즉석 조회가 자동 브리핑 후보를 소모하지 않음.
- 출력된 브리핑을 사용자에게 그대로 전한다. 특정 주제만 원하면 해당 항목만 추려 답한다.

> 특정 항목의 원문이 궁금하면 링크를 안내한다. 수집 JSON 만 보고 싶으면
> `python3 scripts/collect-news.py --days 3 --top 8` 로 확인할 수 있다.

## Pitfalls
- **입력 JSON에 있는 항목만 사용한다. 뉴스를 지어내지 말 것(환각 금지).** 링크·제목·출처·시각을
  임의로 바꾸지 않는다. 이 규칙은 `daily-briefing.md` 의 "절대 지침"과 동일하다.
- 특정 섹션에 해당 항목이 없으면 "오늘은 해당 소식이 없습니다."라고만 적는다(억지로 채우지 않음).
- 같은 사건의 여러 기사는 하나로 합치고 1차/공식 출처를 대표 링크로. 나머지는 "(외 N건)".
- 링크는 Markdown 형식으로만. raw URL 나열 금지. 시각은 `HH:MM KST`.
- 결과가 0건이면(심야/피드 장애) 그 사실을 짧게 알리고 끝낸다.

## Verification
```bash
python3 scripts/collect-news.py --dry-run              # 네트워크 없이 파이프라인 검증(내장 샘플)
python3 scripts/collect-news.py --days 3 --top 5       # 라이브 수집 JSON 확인
python3 scripts/collect-news.py --dry-run --all        # pinned/필터 동작 전체 확인
```
- dry-run 이 3일 필터·중복제거 후 pinned(priority10 공식) 우선 포함해 출력하면 파이프라인 정상.
- 브리핑 초안에 입력 JSON에 없는 기사/링크가 등장하면 재작성(환각).
