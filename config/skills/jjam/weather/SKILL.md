---
name: weather
description: 오늘의 날씨를 조회해 한국어 브리핑으로 전달한다. "날씨", "오늘 우산", "기온", "미세먼지" 등을 물을 때, 그리고 매일 오전 8시 자동 브리핑에 사용.
version: 1.0.0
author: jjam-agent
platforms: [linux, macos]
metadata:
  hermes:
    tags: [weather, briefing, daily]
    category: jjam
    requires_toolsets: [terminal]
required_environment_variables:
  - name: WEATHER_API_KEY
    prompt: OpenWeatherMap API Key
    help: https://openweathermap.org/api 에서 발급. 없으면 mock 데이터로 동작(테스트용).
    required_for: 실제 날씨 데이터(미설정 시 목 데이터로 폴백)
  - name: WEATHER_LOCATION
    prompt: 기본 지역
    help: 미설정 시 '서울'. 예) 부산, 대구
    required_for: 기본 조회 지역 지정(선택)
---

# 날씨 브리핑 (weather)

## When to Use
- 사용자가 오늘 날씨·기온·강수·우산·미세먼지·기상특보를 물을 때.
- 매일 오전 8시(KST) 자동 날씨 브리핑 cron 잡에서 호출될 때.
- 특정 지역을 지정하면(예: "부산 날씨") 그 지역으로 조회한다.

## Procedure
1. 저장소 루트(`terminal.cwd`)에서 날씨 조회 스크립트를 **JSON 모드**로 실행한다:
   ```bash
   python3 scripts/get-weather.py --json                # 기본 지역(WEATHER_LOCATION 또는 서울)
   python3 scripts/get-weather.py --json --location 부산 # 지역 지정 시
   ```
   - `WEATHER_API_KEY` 가 없으면 스크립트가 자동으로 mock 데이터를 반환한다(오류 아님).
2. 출력된 JSON 원자료를 입력으로, **`config/prompts/weather.md`** 의 지침에 따라
   한국어 날씨 브리핑을 작성한다. 핵심: 하루 분위기 한 줄 → 기온/체감/최저최고 →
   강수 시간대(pop≥50%) → 특보 → 옷차림·우산 추천.
3. `source` 가 `mock` 이면 브리핑 끝에 "(참고: 오프라인 예시 데이터입니다)"를 덧붙인다.
4. Discord로 보낼 때 한 메시지 분량(간결, 4~6문장)으로 유지한다.

## Pitfalls
- **JSON에 없는 값을 지어내지 말 것.** `null` 이거나 빈 배열인 항목(미세먼지/특보 등)은
  언급하지 않는다. OWM 무료 forecast는 특보·미세먼지를 제공하지 않아 비어 있을 수 있다.
- `pop` 은 강수확률(%), `rain_mm` 는 예상 강수량(mm)이다. 혼동하지 말 것.
- 스크립트가 비정상 종료(네트워크 오류)하면 `--dry-run` 으로 폴백해 형식만이라도 보여준다.
- 시각은 KST(+09:00) 기준이다.

## Verification
```bash
python3 scripts/get-weather.py --dry-run            # 사람이 읽는 형식
python3 scripts/get-weather.py --dry-run --json     # 스킬이 받는 JSON 스키마
```
- 서울 기본, 기온/강수/추천이 채워져 출력되면 정상.
- 브리핑 초안에 JSON에 없는 수치가 등장하면 재작성(환각).
