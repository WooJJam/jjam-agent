#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jjam-agent — collect-news.py

최근 N시간(기본 24)의 AI/개발 뉴스를 config/sources.yaml 의 RSS/Atom 피드에서
수집하여 중복 제거 후 JSON 으로 출력한다. 출력 JSON 은 Hermes(GPT-5.6 Luna)가
config/prompts/daily-briefing.md 프롬프트로 요약해 Discord 브리핑을 만든다.

사용 예:
    py scripts/collect-news.py                # 기본: 최근 24h, JSON stdout
    py scripts/collect-news.py --hours 12
    py scripts/collect-news.py --dry-run      # 네트워크 없이 내장 샘플로 파이프라인 검증

표준 라이브러리만 사용한다(PyYAML 있으면 사용, 없으면 내장 fallback 파서).
시간대는 KST(UTC+9) 고정: datetime.timezone(timedelta(hours=9)).
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

# ── 상수 ──────────────────────────────────────────────────────
KST = timezone(timedelta(hours=9))
USER_AGENT = "jjam-agent-news-collector/1.0 (+https://github.com/)"
REQUEST_TIMEOUT = 15  # seconds
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCES = os.path.join(ROOT_DIR, "config", "sources.yaml")


def log(msg):
    """경고/진행 로그는 stderr 로(‌stdout 은 JSON 전용)."""
    print(msg, file=sys.stderr)


# ── sources.yaml 로드 (PyYAML 우선, 없으면 fallback) ──────────
def load_sources(path):
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    try:
        import yaml  # type: ignore
        data = yaml.safe_load(text) or {}
        return _normalize_sources(data)
    except ImportError:
        return _normalize_sources(_fallback_parse_yaml(text))


def _normalize_sources(data):
    """{group: [url, ...]} 형태로 정규화. 비어있는 그룹/URL 은 제거."""
    out = {}
    if not isinstance(data, dict):
        return out
    for group, urls in data.items():
        if not isinstance(urls, list):
            continue
        clean = [str(u).strip() for u in urls if str(u).strip()]
        if clean:
            out[str(group).strip()] = clean
    return out


def _fallback_parse_yaml(text):
    """
    아주 단순한 구조만 지원하는 자체 YAML 파서.
        group_name:
          - https://url1
          - https://url2
    주석(#), 빈 줄, 따옴표는 관대하게 처리. 그 외 문법은 지원하지 않음.
    """
    result = {}
    current = None
    for raw in text.splitlines():
        # 주석 제거(URL 안의 #는 드무므로 라인 단위로 처리)
        line = raw.split("#", 1)[0].rstrip()
        if not line.strip():
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("- "):
            # 리스트 항목
            val = stripped[2:].strip().strip("'\"")
            if current is not None and val:
                result.setdefault(current, []).append(val)
        elif stripped.endswith(":") and indent == 0:
            # 그룹 키
            current = stripped[:-1].strip()
            result.setdefault(current, [])
        else:
            # "key: value" 인라인이나 미지원 구조는 무시
            continue
    return result


# ── 네트워크 ─────────────────────────────────────────────────
def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        data = resp.read()
    return data.decode("utf-8", errors="replace")


# ── 날짜 파싱 (RFC822 / ISO8601 모두 시도) ────────────────────
_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
_TZ_NAMES = {
    "UT": 0, "GMT": 0, "UTC": 0, "Z": 0,
    "EST": -5, "EDT": -4, "CST": -6, "CDT": -5,
    "MST": -7, "MDT": -6, "PST": -8, "PDT": -7,
}


def parse_date(raw):
    """다양한 형식의 날짜 문자열을 tz-aware datetime 으로. 실패 시 None."""
    if not raw:
        return None
    s = raw.strip()

    # 1) ISO8601 (Atom updated/published). 'Z' -> +00:00
    iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
    try:
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        pass

    # 2) RFC822 (RSS pubDate): "Wed, 02 Oct 2024 13:00:00 +0000"
    m = re.search(
        r"(\d{1,2})\s+([A-Za-z]{3})[a-z]*\s+(\d{2,4})\s+"
        r"(\d{1,2}):(\d{2})(?::(\d{2}))?\s*"
        r"([+-]\d{4}|[A-Za-z]{2,4})?",
        s,
    )
    if m:
        day, mon, year, hh, mm, ss, tz = m.groups()
        mon_num = _MONTHS.get(mon.lower()[:3])
        if mon_num:
            year = int(year)
            if year < 100:
                year += 2000
            offset = timezone.utc
            if tz:
                if re.match(r"^[+-]\d{4}$", tz):
                    sign = 1 if tz[0] == "+" else -1
                    offset = timezone(sign * timedelta(
                        hours=int(tz[1:3]), minutes=int(tz[3:5])))
                elif tz.upper() in _TZ_NAMES:
                    offset = timezone(timedelta(hours=_TZ_NAMES[tz.upper()]))
            try:
                return datetime(
                    year, mon_num, int(day), int(hh), int(mm),
                    int(ss or 0), tzinfo=offset)
            except ValueError:
                return None
    return None


# ── 피드 파싱 (RSS + Atom) ───────────────────────────────────
def _tag(el):
    """네임스페이스 제거한 로컬 태그명."""
    t = el.tag
    return t.split("}", 1)[1] if "}" in t else t


def _find_text(item, names):
    for child in item:
        if _tag(child).lower() in names:
            if child.text and child.text.strip():
                return child.text.strip()
    return None


def _find_link(item):
    # RSS: <link>text</link>. Atom: <link href="..." rel="alternate"/>
    alt = None
    first = None
    for child in item:
        if _tag(child).lower() != "link":
            continue
        href = child.get("href")
        if href:
            rel = (child.get("rel") or "alternate").lower()
            if rel == "alternate":
                alt = alt or href
            first = first or href
        elif child.text and child.text.strip():
            return child.text.strip()
    return alt or first


def parse_feed(xml_text, source_label):
    """RSS/Atom XML 문자열 -> [{title, url, published(datetime|None), source}]."""
    items = []
    try:
        root = ET.fromstring(xml_text.encode("utf-8"))
    except ET.ParseError as e:
        raise ValueError("XML parse error: %s" % e)

    # RSS: channel/item, Atom: entry
    entries = []
    for el in root.iter():
        if _tag(el).lower() in ("item", "entry"):
            entries.append(el)

    for it in entries:
        title = _find_text(it, {"title"})
        link = _find_link(it)
        pub_raw = _find_text(it, {"pubdate", "published", "updated", "date"})
        if not title or not link:
            continue
        items.append({
            "title": html.unescape(title).strip(),
            "url": link.strip(),
            "published_dt": parse_date(pub_raw),
            "published_raw": pub_raw,
            "source": source_label,
        })
    return items


# ── URL 정규화 & 중복 제거 ───────────────────────────────────
_TRACKING_PARAM = re.compile(r"^(utm_|fbclid|gclid|mc_|ref|source$)", re.I)


def normalize_url(url):
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        parts = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    scheme = parts.scheme.lower() or "https"
    path = parts.path.rstrip("/")
    q = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
         if not _TRACKING_PARAM.match(k)]
    query = urlencode(sorted(q))
    return urlunsplit((scheme, host, path, query, ""))


def _title_key(title):
    """제목 유사 중복 판정용 정규화 키(영숫자/한글 소문자만)."""
    t = title.lower()
    t = re.sub(r"[^0-9a-z가-힣]+", "", t)
    return t


def dedupe(items):
    seen_url = set()
    seen_title = set()
    out = []
    for it in items:
        ukey = normalize_url(it["url"])
        tkey = _title_key(it["title"])
        if ukey in seen_url or (tkey and tkey in seen_title):
            continue
        seen_url.add(ukey)
        if tkey:
            seen_title.add(tkey)
        out.append(it)
    return out


# ── 파이프라인 ───────────────────────────────────────────────
def within_hours(item, hours, now):
    dt = item.get("published_dt")
    if dt is None:
        # 시각 파싱 실패 항목은 보수적으로 제외(24h 확신 불가)
        return False
    return (now - dt) <= timedelta(hours=hours) and dt <= now + timedelta(minutes=5)


def build_output(grouped_items, hours):
    """{group: [feed items...]} -> 필터/중복제거/정렬된 최종 리스트.

    중복 제거는 그룹 간 경계 없이 전역으로 수행한다(같은 사건이 여러 그룹
    피드에 걸쳐 올라와도 1건만 남긴다). 최신 항목이 대표로 남도록 시각
    내림차순으로 먼저 정렬한 뒤 중복 제거한다.
    """
    now = datetime.now(KST)

    # 1) 그룹 순서를 보존하며 평탄화 + 24h 필터
    group_order = list(grouped_items.keys())
    flat = []
    for group in group_order:
        for it in grouped_items[group]:
            if within_hours(it, hours, now):
                it = dict(it)
                it["group"] = group
                flat.append(it)

    # 2) 최신순 정렬 후 전역 중복 제거(최신 대표 유지)
    flat.sort(key=lambda x: x["published_dt"], reverse=True)
    flat = dedupe(flat)

    # 3) 그룹별로 모아 그룹 순서 -> 그룹 내 최신순으로 출력
    by_group = {g: [] for g in group_order}
    for it in flat:
        by_group[it["group"]].append(it)

    result = []
    for group in group_order:
        for it in by_group[group]:
            result.append({
                "group": group,
                "title": it["title"],
                "url": it["url"],
                "published": it["published_dt"].astimezone(KST).isoformat(),
                "source": it["source"],
            })
    return result


def source_label(url):
    from urllib.parse import urlsplit
    host = urlsplit(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def collect_live(sources, hours):
    grouped = {}
    for group, urls in sources.items():
        grouped.setdefault(group, [])
        for url in urls:
            try:
                xml_text = fetch(url)
                items = parse_feed(xml_text, source_label(url))
                grouped[group].extend(items)
                log("  [ok] %-40s %d개" % (source_label(url), len(items)))
            except (urllib.error.URLError, urllib.error.HTTPError,
                    ValueError, TimeoutError, OSError) as e:
                log("  [skip] %s -> %s" % (url, e))
                continue
    return grouped


# ── --dry-run 내장 샘플 ──────────────────────────────────────
def _sample_feeds():
    """네트워크 없이 파이프라인 검증용. now(KST) 기준으로 상대 시각 생성."""
    now = datetime.now(KST)

    def rfc822(delta):
        dt = (now - delta).astimezone(timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")

    def iso(delta):
        return (now - delta).astimezone(timezone.utc).replace(
            microsecond=0).isoformat().replace("+00:00", "Z")

    # RSS 2.0 샘플: 최신 2건 + 24h 초과 1건 + 중복(URL/utm 차이) 1건
    rss = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
  <title>Sample Dev News</title>
  <item>
    <title>새 JDK 25 릴리스 후보 공개</title>
    <link>https://example.com/jdk-25-rc?utm_source=rss&amp;utm_medium=feed</link>
    <pubDate>{recent1}</pubDate>
  </item>
  <item>
    <title>Kubernetes 1.33 보안 패치</title>
    <link>https://www.example.com/k8s-133-security/</link>
    <pubDate>{recent2}</pubDate>
  </item>
  <item>
    <title>오래된 뉴스 - 필터되어야 함</title>
    <link>https://example.com/old-news</link>
    <pubDate>{old}</pubDate>
  </item>
  <item>
    <title>새 JDK 25 릴리스 후보 공개</title>
    <link>https://example.com/jdk-25-rc</link>
    <pubDate>{recent1}</pubDate>
  </item>
</channel></rss>""".format(
        recent1=rfc822(timedelta(hours=2)),
        recent2=rfc822(timedelta(hours=6)),
        old=rfc822(timedelta(hours=40)),
    )

    # Atom 샘플: 최신 1건 + 위 RSS 와 제목이 동일한 유사 중복 1건
    atom = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Sample Spring Blog</title>
  <entry>
    <title>Spring Boot 3.5 GA 발표</title>
    <link rel="alternate" href="https://spring.example.io/blog/boot-35-ga"/>
    <updated>{recent}</updated>
  </entry>
  <entry>
    <title>Kubernetes 1.33 보안 패치</title>
    <link rel="alternate" href="https://another.example.io/k8s-133-security"/>
    <updated>{dup}</updated>
  </entry>
</feed>""".format(
        recent=iso(timedelta(hours=1)),
        dup=iso(timedelta(hours=5)),
    )

    return {
        "java_openjdk": [("sample-rss.example.com", rss)],
        "spring": [("sample-atom.example.io", atom)],
    }


def collect_dry_run(hours):
    grouped = {}
    for group, feeds in _sample_feeds().items():
        grouped.setdefault(group, [])
        for label, xml_text in feeds:
            items = parse_feed(xml_text, label)
            grouped[group].extend(items)
            log("  [sample] %-30s %d개" % (label, len(items)))
    return grouped


# ── main ─────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="AI/개발 뉴스 RSS 수집 -> 24h 필터/중복제거 -> JSON")
    ap.add_argument("--hours", type=int, default=24,
                    help="수집 대상 최근 시간(기본 24)")
    ap.add_argument("--sources", default=DEFAULT_SOURCES,
                    help="sources.yaml 경로")
    ap.add_argument("--json", action="store_true", default=True,
                    help="JSON 출력(기본)")
    ap.add_argument("--dry-run", action="store_true",
                    help="네트워크 없이 내장 샘플로 파이프라인 검증")
    args = ap.parse_args(argv)

    if args.dry_run:
        log("[dry-run] 내장 샘플 피드 파싱...")
        grouped = collect_dry_run(args.hours)
    else:
        try:
            sources = load_sources(args.sources)
        except OSError as e:
            log("[error] sources 로드 실패: %s" % e)
            return 1
        if not sources:
            log("[error] 유효한 소스가 없습니다: %s" % args.sources)
            return 1
        total = sum(len(v) for v in sources.values())
        log("[collect] %d개 그룹, %d개 피드 수집 중(최근 %dh)..."
            % (len(sources), total, args.hours))
        grouped = collect_live(sources, args.hours)

    output = build_output(grouped, args.hours)
    log("[done] 최종 %d개 항목(필터/중복제거 후)" % len(output))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
