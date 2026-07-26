#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""jjam-agent — collect-news.py  (AI·개발 브리핑 수집기)

config/sources.yml 의 소스들을 세 방법으로 수집한다:
  1) RSS/Atom     : 대부분의 공식 블로그/뉴스
  2) GitHub 릴리스 : type=github-release → <repo>/releases.atom
  3) Brave Search  : RSS 없는 소스(Anthropic/Meta/Reuters 등). BRAVE_API_KEY 필요.

수집 → 최근 N일(기본 3) 필터 → 중복 제거 → priority 기준 상위 K개(기본 5) → JSON(stdout).
이 JSON 을 브리핑 생성 단계(scripts/make-briefing.py)가 받아 요약한다.

사용 예:
    python3 scripts/collect-news.py                 # 최근 3일, 상위 5개
    python3 scripts/collect-news.py --days 2 --top 8
    python3 scripts/collect-news.py --dry-run       # 네트워크 없이 내장 샘플로 검증
    python3 scripts/collect-news.py --all           # top 제한 없이 전체 출력(디버그)

시간대는 KST(UTC+9) 고정. sources.yml 파싱에 PyYAML 이 필요하다(requirements.txt).
"""

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))
USER_AGENT = "jjam-agent-news-collector/2.0"
REQUEST_TIMEOUT = 15
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SOURCES = os.path.join(ROOT_DIR, "config", "sources.yml")
BRAVE_ENDPOINT = "https://api.search.brave.com/res/v1/web/search"


def log(msg):
    print(msg, file=sys.stderr)


# ── 소스 id → RSS/Atom 피드 주소 (라이브 검증됨) ───────────────
# sources.yml 의 url 은 사람이 보는 페이지라, 실제 피드 주소는 여기서 해석한다.
# 여기에 없고 github-release 도 아니면 Brave Search 로 폴백한다.
FEED_URLS = {
    "openai_news": "https://openai.com/news/rss.xml",
    "huggingface_blog": "https://huggingface.co/blog/feed.xml",
    "google_ai_blog": "https://blog.google/technology/ai/rss/",
    "google_cloud_ai": "https://cloudblog.withgoogle.com/products/ai-machine-learning/rss/",
    "spring_blog": "https://spring.io/blog.atom",
    "inside_java": "https://inside.java/feed.xml",
    "infoq_java": "https://feed.infoq.com/java/",
    "github_blog": "https://github.blog/feed/",
    "docker_blog": "https://www.docker.com/blog/feed/",
    "kubernetes_blog": "https://kubernetes.io/feed.xml",
    "cloudflare_blog": "https://blog.cloudflare.com/rss/",
    "aws_ml_blog": "https://aws.amazon.com/blogs/machine-learning/feed/",
    "aws_architecture_blog": "https://aws.amazon.com/blogs/architecture/feed/",
    "arxiv_ai": "http://export.arxiv.org/rss/cs.AI",
    "arxiv_se": "http://export.arxiv.org/rss/cs.SE",
    "techcrunch_ai": "https://techcrunch.com/category/artificial-intelligence/feed/",
    "hackernews": "https://hnrss.org/frontpage?points=100",
}


# ── sources.yml 로드 (PyYAML 필요) ────────────────────────────
def load_sources(path):
    try:
        import yaml  # type: ignore
    except ImportError:
        log("[error] PyYAML 이 필요합니다: python3 -m pip install -r requirements.txt")
        raise SystemExit(2)
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    items = data.get("sources", []) if isinstance(data, dict) else []
    out = []
    for s in items:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        out.append({
            "id": str(s["id"]).strip(),
            "name": str(s.get("name", s["id"])).strip(),
            "type": str(s.get("type", "news")).strip(),
            "category": str(s.get("category", "")).strip(),
            "url": str(s.get("url", "")).strip(),
            "priority": int(s.get("priority", 5)),
        })
    return out


# ── 수집 방법 결정 ────────────────────────────────────────────
def resolve_method(src):
    """(method, feed_url) 반환. method: 'rss' | 'brave'."""
    if src["id"] in FEED_URLS:
        return "rss", FEED_URLS[src["id"]]
    if src["type"] == "github-release":
        # https://github.com/OWNER/REPO/releases → .../releases.atom
        u = src["url"].rstrip("/")
        if u.endswith("/releases"):
            return "rss", u + ".atom"
        return "rss", u.rstrip("/") + "/releases.atom"
    return "brave", None


# ── 네트워크 ─────────────────────────────────────────────────
def fetch(url, headers=None):
    h = {"User-Agent": USER_AGENT}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        return resp.read()


# ── 날짜 파싱 (ISO8601 / RFC822) ─────────────────────────────
def parse_date(raw):
    if not raw:
        return None
    s = raw.strip()
    try:
        iso = s.replace("Z", "+00:00") if s.endswith("Z") else s
        dt = datetime.fromisoformat(iso)
        return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except ValueError:
        pass
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
    except (TypeError, ValueError):
        pass
    return None


# ── 피드 파싱 (RSS + Atom) ───────────────────────────────────
def _tag(el):
    t = el.tag
    return t.split("}", 1)[1] if "}" in t else t


def _find_text(item, names):
    for child in item:
        if _tag(child).lower() in names and child.text and child.text.strip():
            return child.text.strip()
    return None


def _find_link(item):
    alt = first = None
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


def parse_feed(xml_bytes):
    """RSS/Atom → [{title, url, published_dt}]."""
    root = ET.fromstring(xml_bytes)
    entries = [el for el in root.iter() if _tag(el).lower() in ("item", "entry")]
    items = []
    for it in entries:
        title = _find_text(it, {"title"})
        link = _find_link(it)
        pub = _find_text(it, {"pubdate", "published", "updated", "date"})
        if not title or not link:
            continue
        items.append({
            "title": html.unescape(title).strip(),
            "url": link.strip(),
            "published_dt": parse_date(pub),
        })
    return items


# ── Brave Search 수집 (RSS 없는 소스) ────────────────────────
def brave_search(src, days, api_key):
    """소스 도메인 한정 최근 글을 Brave 로 검색. 실패/키없음 시 []。"""
    if not api_key:
        return []
    host = urllib.parse.urlsplit(src["url"]).netloc
    # 최근성: 3일 이내면 pd(past day) 부족 → pw(past week)로 받고 아래 3일 필터로 정밀화
    freshness = "pw" if days > 1 else "pd"
    q = "site:%s" % host
    params = urllib.parse.urlencode({
        "q": q, "count": 10, "freshness": freshness, "result_filter": "web",
    })
    try:
        raw = fetch("%s?%s" % (BRAVE_ENDPOINT, params),
                    headers={"X-Subscription-Token": api_key,
                             "Accept": "application/json"})
        data = json.loads(raw.decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, ValueError, TimeoutError) as e:
        log("  [brave-skip] %s -> %s" % (src["id"], e))
        return []
    results = (data.get("web", {}) or {}).get("results", []) or []
    items = []
    for r in results:
        title, url = r.get("title"), r.get("url")
        if not title or not url:
            continue
        items.append({
            "title": html.unescape(title).strip(),
            "url": url.strip(),
            "published_dt": parse_date(r.get("page_age") or r.get("age")),
        })
    return items


# ── URL 정규화 & 중복 제거 ───────────────────────────────────
_TRACKING = re.compile(r"^(utm_|fbclid|gclid|mc_|ref|source$)", re.I)


def normalize_url(url):
    from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
    try:
        p = urlsplit(url.strip())
    except ValueError:
        return url.strip().lower()
    host = p.netloc.lower()
    host = host[4:] if host.startswith("www.") else host
    q = [(k, v) for k, v in parse_qsl(p.query) if not _TRACKING.match(k)]
    return urlunsplit((p.scheme.lower() or "https", host, p.path.rstrip("/"),
                       urlencode(sorted(q)), ""))


def _title_key(t):
    return re.sub(r"[^0-9a-z가-힣]+", "", t.lower())


def dedupe(items):
    seen_u, seen_t, out = set(), set(), []
    for it in items:
        uk, tk = normalize_url(it["url"]), _title_key(it["title"])
        if uk in seen_u or (tk and tk in seen_t):
            continue
        seen_u.add(uk)
        if tk:
            seen_t.add(tk)
        out.append(it)
    return out


# ── 파이프라인 ───────────────────────────────────────────────
# priority 가 이 값 이상인 "공식 발표/릴리스"는 top 제한과 무관하게 항상 포함한다.
# (예: OpenAI/Anthropic News, Spring 블로그·Spring AI 릴리스 — 자주 안 나와도 나오면 반드시 전달)
PIN_PRIORITY = 10
PINNED_TYPES = ("official", "github-release")


def within_days(item, days, now):
    """모든 소스에 동일 적용: 게시일이 최근 days일 이내여야 통과.
    날짜를 확인할 수 없는 항목은 '3일 이내'를 확증할 수 없으므로 제외한다."""
    dt = item.get("published_dt")
    if dt is None:
        return False
    dt = dt.astimezone(KST)
    return (now - dt) <= timedelta(days=days) and dt <= now + timedelta(minutes=5)


def collect(sources, days, brave_key):
    now = datetime.now(KST)
    collected = []
    for src in sources:
        method, feed_url = resolve_method(src)
        try:
            if method == "rss":
                raw = fetch(feed_url)
                raw_items = parse_feed(raw)
            else:
                if not brave_key:
                    log("  [skip] %-22s RSS 없음 · BRAVE_API_KEY 미설정" % src["id"])
                    continue
                raw_items = brave_search(src, days, brave_key)
        except (urllib.error.URLError, urllib.error.HTTPError,
                ValueError, TimeoutError, OSError, ET.ParseError) as e:
            log("  [skip] %-22s -> %s" % (src["id"], e))
            continue

        kept = dropped = 0
        for it in raw_items:
            if not within_days(it, days, now):
                dropped += 1
                continue
            dt = it["published_dt"].astimezone(KST)
            collected.append({
                "source_id": src["id"],
                "source": src["name"],
                "type": src["type"],
                "category": src["category"],
                "priority": src["priority"],
                "title": it["title"],
                "url": it["url"],
                "published": dt.isoformat(),
                "_sort_dt": dt,
            })
            kept += 1
        note = "" if not dropped else " (기간외/무날짜 %d개 제외)" % dropped
        log("  [%s] %-22s %d개(최근 %d일)%s" % (method, src["id"], kept, days, note))
    return collected


def rank_and_trim(items, top):
    """중복 제거 → 핵심 공식 발표는 항상 포함(pinned) → 나머지 자리를 priority·최신순으로 채움.

    - pinned: priority>=PIN_PRIORITY 인 official/github-release (OpenAI/Anthropic News,
      Spring 블로그·Spring AI 릴리스 등). 자주 안 나와도 3일 내 나오면 top 제한과 무관하게 전달.
    - 나머지: priority 내림차순(동률은 최신순)으로 (top - pinned수)만큼 채움.
    - pinned 가 top 보다 많아도 절대 버리지 않는다(중요 소식 누락 방지).
    """
    items = dedupe(items)
    items.sort(key=lambda x: (x["priority"], x["_sort_dt"]), reverse=True)

    pinned = [it for it in items
              if it["priority"] >= PIN_PRIORITY and it.get("type") in PINNED_TYPES]
    pinned_marker = {id(it) for it in pinned}
    rest = [it for it in items if id(it) not in pinned_marker]

    if top and top > 0:
        fill = rest[:max(0, top - len(pinned))]
    else:
        fill = rest
    chosen = pinned + fill
    chosen.sort(key=lambda x: (x["priority"], x["_sort_dt"]), reverse=True)
    for it in chosen:
        it.pop("_sort_dt", None)
    return chosen


# ── --dry-run 내장 샘플(네트워크 없이 파이프라인 검증) ───────
def _dry_run(days, top):
    now = datetime.now(KST)

    def iso(h):
        return (now - timedelta(hours=h)).isoformat()
    samples = [
        # (id, name, type, category, priority, title, url, hours_ago)
        ("openai_news", "OpenAI News", "official", "ai", 10, "GPT-5.6 Luna 업데이트 공개", "https://openai.com/news/luna", 5),
        ("spring_ai_releases", "Spring AI GitHub Releases", "github-release", "spring-ai", 10, "Spring AI 1.2.0 릴리스", "https://github.com/spring-projects/spring-ai/releases/tag/v1.2.0", 20),
        ("anthropic_news", "Anthropic News", "official", "ai", 10, "Claude 새 기능 발표", "https://anthropic.com/news/x", 30),
        ("hackernews", "Hacker News", "community", "developer-trend", 5, "Show HN: 어떤 도구", "https://news.ycombinator.com/item?id=1", 10),
        ("arxiv_ai", "arXiv CS.AI", "research", "ai-research", 6, "새 LLM 에이전트 논문", "https://arxiv.org/abs/2607.00001", 2),
        ("infoq_java", "InfoQ Java", "news", "java", 7, "JDK 26 프리뷰 정리", "https://infoq.com/java/jdk26", 8),
        ("old_item", "Old Source", "news", "misc", 9, "오래된 글(필터되어야 함)", "https://example.com/old", 24 * 10),
    ]
    items = []
    for sid, name, stype, cat, pri, title, url, h in samples:
        items.append({
            "source_id": sid, "source": name, "type": stype, "category": cat,
            "priority": pri, "title": title, "url": url, "published": iso(h),
            "_sort_dt": now - timedelta(hours=h),
        })
    items = [i for i in items if (now - i["_sort_dt"]) <= timedelta(days=days)]
    return rank_and_trim(items, top)


# ── main ─────────────────────────────────────────────────────
def main(argv=None):
    ap = argparse.ArgumentParser(description="AI·개발 뉴스 수집 → 최근 N일 필터/중복제거 → priority top-K → JSON")
    ap.add_argument("--sources", default=DEFAULT_SOURCES, help="sources.yml 경로")
    ap.add_argument("--days", type=int, default=3, help="최근 N일(기본 3)")
    ap.add_argument("--top", type=int, default=5, help="상위 K개만 출력(기본 5)")
    ap.add_argument("--all", action="store_true", help="top 제한 없이 전체 출력(디버그)")
    ap.add_argument("--dry-run", action="store_true", help="네트워크 없이 내장 샘플로 검증")
    args = ap.parse_args(argv)

    top = 0 if args.all else args.top

    if args.dry_run:
        log("[dry-run] 내장 샘플로 파이프라인 검증...")
        output = _dry_run(args.days, top)
    else:
        sources = load_sources(args.sources)
        if not sources:
            log("[error] 유효한 소스가 없습니다: %s" % args.sources)
            return 1
        brave_key = os.environ.get("BRAVE_API_KEY")
        log("[collect] %d개 소스 수집(최근 %d일)%s..."
            % (len(sources), args.days,
               "" if brave_key else " · BRAVE_API_KEY 없음(RSS만)"))
        collected = collect(sources, args.days, brave_key)
        output = rank_and_trim(collected, top)

    log("[done] 최종 %d개(priority top%s)" % (len(output), "∞" if top == 0 else str(top)))
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
