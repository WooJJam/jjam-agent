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
- 사용자가 오늘/최근 개발 뉴스, AI·IT 소식, Java·Spring·백엔드·클라우드·보안 업데이트를 물을 때.
- 매일 오전 9시(KST) 자동 뉴스 브리핑 cron 잡에서 호출될 때.
- 기간을 좁히려면(예: "최근 12시간") `--hours` 로 조정.

## Procedure
1. 저장소 루트(`terminal.cwd`)에서 뉴스 수집 스크립트를 실행한다(stdout=JSON, stderr=로그):
   ```bash
   python3 scripts/collect-news.py --hours 24
   ```
   - `config/sources.yaml` 의 RSS/Atom 피드를 수집해 **24h 필터 + URL/제목 중복제거**한
     JSON 배열을 출력한다. 각 항목: `group`, `title`, `url`, `published`(KST), `source`.
   - 일부 피드가 죽어 있어도(네트워크/파싱 오류) 해당 피드만 건너뛰고 계속한다.
2. 출력 JSON을 입력으로, **`config/prompts/daily-briefing.md`** 의 지침에 따라 5개 섹션
   브리핑을 작성한다: ① 오늘 꼭 볼 소식 ② Java·Spring ③ 백엔드·인프라
   ④ 오늘 시도해볼 아이디어 ⑤ 한 줄 결론.
3. Discord 전송 시 한 메시지 ~1500자 이내로 압축하고, 넘치면 섹션 경계에서 분할한다.

## Pitfalls
- **입력 JSON에 있는 항목만 사용한다. 뉴스를 지어내지 말 것(환각 금지).** 링크·제목·출처·시각을
  임의로 바꾸지 않는다. 이 규칙은 `daily-briefing.md` 의 "절대 지침"과 동일하다.
- 특정 섹션에 해당 항목이 없으면 "오늘은 해당 소식이 없습니다."라고만 적는다(억지로 채우지 않음).
- 같은 사건의 여러 기사는 하나로 합치고 1차/공식 출처를 대표 링크로. 나머지는 "(외 N건)".
- 링크는 Markdown 형식으로만. raw URL 나열 금지. 시각은 `HH:MM KST`.
- 결과가 0건이면(심야/피드 장애) 그 사실을 짧게 알리고 끝낸다.

## Verification
```bash
python3 scripts/collect-news.py --dry-run          # 네트워크 없이 파이프라인 검증(내장 샘플)
python3 scripts/collect-news.py --hours 24 | head  # 라이브 수집 JSON 확인
```
- dry-run 이 24h 필터·중복제거 후 항목을 출력하면 파이프라인 정상.
- 브리핑 초안에 입력 JSON에 없는 기사/링크가 등장하면 재작성(환각).
