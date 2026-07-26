#!/usr/bin/env python3
"""오늘의 날씨 조회 도구 (jjam-agent / weather).

Hermes 런타임이 호출하지만 단독 실행도 가능하다.
표준 라이브러리만 사용하며, WEATHER_API_KEY가 없거나 --dry-run이면
목(mock) 데이터로 오프라인 완전 실행된다.

사용 예:
    py scripts/get-weather.py
    py scripts/get-weather.py --dry-run
    py scripts/get-weather.py --dry-run --json
    py scripts/get-weather.py --location 부산
"""

import argparse
import datetime
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

# Asia/Seoul (zoneinfo 대신 고정 오프셋 사용: Windows tzdata 의존 회피)
KST = datetime.timezone(datetime.timedelta(hours=9))

DEFAULT_LOCATION = "서울"
OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"


def _now_kst():
    return datetime.datetime.now(KST)


def build_mock(location):
    """오프라인/키 없음일 때 사용할 목 데이터. 실제 fetch 결과와 동일한 스키마."""
    now = _now_kst()
    hourly = []
    # 오후에 강수확률이 높아지는 가상의 시간대별 데이터
    pops = {12: 10, 13: 20, 14: 40, 15: 70, 16: 65, 17: 60, 18: 55, 19: 20}
    for hour in range(now.hour, min(now.hour + 12, 24)):
        pop = pops.get(hour, 10)
        hourly.append({
            "time": "%02d시" % hour,
            "hour": hour,
            "pop": pop,                       # 강수확률(%)
            "rain_mm": round(pop / 20.0, 1),  # 예상 강수량(mm)
        })
    return {
        "location": location,
        "observed_at": now.isoformat(),
        "source": "mock",
        "current_temp": 24,
        "feels_like": 26,
        "temp_min": 21,
        "temp_max": 31,
        "humidity": 60,
        "wind_speed": 3,
        "hourly": hourly,
        "air_quality": "보통",          # 미세먼지(선택)
        "alerts": ["오후 소나기 가능"],  # 기상특보/특이사항(선택)
    }


def _parse_owm(raw, location):
    """OpenWeatherMap 5day/3hour forecast 응답 -> 내부 스키마.

    OWM 무료 forecast는 특보/미세먼지를 제공하지 않으므로 해당 항목은 비워둔다.
    """
    entries = raw.get("list", [])
    if not entries:
        raise ValueError("예보 데이터가 비어 있습니다.")

    now = _now_kst()
    today = now.date()
    first = entries[0].get("main", {})

    temps = []
    hourly = []
    for e in entries:
        dt = datetime.datetime.fromtimestamp(e.get("dt", 0), KST)
        main = e.get("main", {})
        if dt.date() == today:
            if "temp_min" in main:
                temps.append(main["temp_min"])
            if "temp_max" in main:
                temps.append(main["temp_max"])
            pop = int(round(e.get("pop", 0) * 100))
            rain_mm = round(e.get("rain", {}).get("3h", 0.0), 1)
            hourly.append({
                "time": "%02d시" % dt.hour,
                "hour": dt.hour,
                "pop": pop,
                "rain_mm": rain_mm,
            })

    wind = entries[0].get("wind", {})
    return {
        "location": location,
        "observed_at": now.isoformat(),
        "source": "openweathermap",
        "current_temp": round(first.get("temp")) if first.get("temp") is not None else None,
        "feels_like": round(first.get("feels_like")) if first.get("feels_like") is not None else None,
        "temp_min": round(min(temps)) if temps else None,
        "temp_max": round(max(temps)) if temps else None,
        "humidity": first.get("humidity"),
        "wind_speed": round(wind.get("speed", 0)),
        "hourly": hourly,
        "air_quality": None,
        "alerts": [],
    }


def fetch_weather(location, api_key):
    """실제 API(OpenWeatherMap 가정) 호출. 실패 시 예외를 던진다."""
    params = urllib.parse.urlencode({
        "q": location,
        "appid": api_key,
        "units": "metric",
        "lang": "kr",
    })
    url = "%s?%s" % (OWM_URL, params)
    req = urllib.request.Request(url, headers={"User-Agent": "jjam-agent-weather/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        raw = json.loads(resp.read().decode("utf-8"))
    return _parse_owm(raw, location)


def get_weather(location, api_key, dry_run):
    """dry_run이거나 키가 없으면 목 데이터, 아니면 실제 호출."""
    if dry_run or not api_key:
        return build_mock(location)
    return fetch_weather(location, api_key)


def _rain_window(hourly):
    """강수확률 50% 이상 구간과 최고 강수확률을 반환."""
    rainy = [h for h in hourly if h["pop"] >= 50]
    if not rainy:
        return None
    start = rainy[0]["time"]
    end = "%02d시" % (rainy[-1]["hour"] + 1)
    peak = max(h["pop"] for h in rainy)
    return start, end, peak


def _recommend(data):
    tips = []
    window = _rain_window(data["hourly"])
    if window:
        tips.append("우산 준비")
        tips.append("야외 일정은 오전 권장")
    if data.get("temp_max") is not None and data["temp_max"] >= 30:
        tips.append("더위 대비(물, 가벼운 옷차림)")
    if data.get("temp_min") is not None and data["temp_min"] <= 5:
        tips.append("따뜻하게 입기")
    if not tips:
        tips.append("특별한 준비물 없음")
    return ", ".join(tips)


def format_text(data):
    lines = []
    lines.append("[오늘의 날씨] (%s)" % data["location"])

    cur = data.get("current_temp")
    feel = data.get("feels_like")
    if cur is not None and feel is not None:
        lines.append("- 현재: %d℃ (체감 %d℃)" % (cur, feel))
    elif cur is not None:
        lines.append("- 현재: %d℃" % cur)

    lo, hi = data.get("temp_min"), data.get("temp_max")
    if lo is not None and hi is not None:
        lines.append("- 최저/최고: %d℃ / %d℃" % (lo, hi))

    window = _rain_window(data.get("hourly", []))
    if window:
        start, end, peak = window
        lines.append("- 비 가능 시간: %s~%s (최고 강수확률 %d%%)" % (start, end, peak))
    else:
        lines.append("- 비 가능 시간: 없음 (종일 대체로 맑음)")

    hum, wind = data.get("humidity"), data.get("wind_speed")
    if hum is not None and wind is not None:
        lines.append("- 습도/풍속: %d%% / %dm/s" % (hum, wind))

    if data.get("air_quality"):
        lines.append("- 미세먼지: %s" % data["air_quality"])

    alerts = data.get("alerts") or []
    if alerts:
        lines.append("- 특이사항: %s" % ", ".join(alerts))

    lines.append("- 추천: %s" % _recommend(data))
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="오늘의 날씨 조회 (jjam-agent)")
    parser.add_argument("--location", default=None, help="조회 지역 (기본: 환경변수 WEATHER_LOCATION 또는 '서울')")
    parser.add_argument("--dry-run", action="store_true", help="목 데이터로 오프라인 실행")
    parser.add_argument("--json", action="store_true", dest="as_json", help="원자료를 JSON으로 출력")
    args = parser.parse_args(argv)

    location = args.location or os.environ.get("WEATHER_LOCATION") or DEFAULT_LOCATION
    api_key = os.environ.get("WEATHER_API_KEY")

    try:
        data = get_weather(location, api_key, args.dry_run)
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as exc:
        sys.stderr.write("날씨 정보를 가져오지 못했습니다: %s\n" % exc)
        sys.stderr.write("오프라인에서 확인하려면 --dry-run 옵션을 사용하세요.\n")
        return 1
    except Exception as exc:  # noqa: BLE001 - 사용자 친화적 최종 방어
        sys.stderr.write("예상치 못한 오류가 발생했습니다: %s\n" % exc)
        return 1

    if args.as_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(format_text(data))
    return 0


if __name__ == "__main__":
    sys.exit(main())
