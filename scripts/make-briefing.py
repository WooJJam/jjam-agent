#!/usr/bin/env python3
"""jjam-agent — make-briefing.py  (브리핑 생성·전송 파이프라인)

흐름:
  collect-news.py 실행(수집→3일 필터→중복제거→이미보낸것 제외→priority top-N)
    → 카테고리별 버킷(핵심 AI / Java·Spring / 기타)
    → OpenAI API 로 config/prompts/daily-briefing.md 형식 브리핑 생성
    → Discord Webhook 전송
    → 전송 성공 시 sent_store.mark_sent (다음날 중복 발송 방지)

환경변수:
  OPENAI_API_KEY        (필수, --dry-run 제외)   OPENAI_BASE_URL(선택, 기본 api.openai.com/v1)
  DEFAULT_MODEL         (기본 gpt-5.6-luna)
  DISCORD_WEBHOOK_URL   (없으면 전송 대신 콘솔 출력 + 기록 생략)

사용 예:
  python3 scripts/make-briefing.py                 # 실제: 수집→요약→전송→기록
  python3 scripts/make-briefing.py --dry-run       # 오프라인: 수집 샘플로 프롬프트/버킷만 확인(요약·전송·기록 없음)
  python3 scripts/make-briefing.py --no-send       # 요약까지 하되 전송/기록은 안 함(콘솔 출력)
  python3 scripts/make-briefing.py --top 10 --days 3
"""

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
PROMPT_FILE = os.path.join(ROOT_DIR, "config", "prompts", "daily-briefing.md")
COLLECTOR = os.path.join(SCRIPTS_DIR, "collect-news.py")

OPENAI_BASE = (os.environ.get("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
MODEL = os.environ.get("DEFAULT_MODEL", "gpt-5.6-luna")
DISCORD_LIMIT = 1900  # Discord 2000자 한도 여유

# 카테고리 → 섹션 버킷
CORE_AI = {"ai", "cloud-ai", "ai-api", "open-source-ai", "ai-news", "ai-research"}
JAVA_SPRING = {"java", "spring", "spring-ai", "java-ai"}


def log(msg):
    print(msg, file=sys.stderr)


def section_of(category):
    if category in CORE_AI:
        return "core_ai"
    if category in JAVA_SPRING:
        return "java_spring"
    return "etc"


def run_collector(days, top, dry_run):
    """collect-news.py 를 실행해 선별된 항목 리스트(JSON)를 얻는다."""
    cmd = [sys.executable, COLLECTOR, "--days", str(days), "--top", str(top)]
    if dry_run:
        cmd.append("--dry-run")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        log(proc.stderr.strip())
        raise SystemExit("수집 실패(collect-news.py)")
    # 진행 로그(stderr)는 그대로 흘려보내 사용자도 보게 한다.
    if proc.stderr.strip():
        log(proc.stderr.rstrip())
    return json.loads(proc.stdout or "[]")


def bucketize(items):
    buckets = {"core_ai": [], "java_spring": [], "etc": []}
    for it in items:
        buckets[section_of(it.get("category", ""))].append({
            "source": it.get("source"),
            "title": it.get("title"),
            "url": it.get("url"),
            "published": it.get("published"),
            "category": it.get("category"),
            "priority": it.get("priority"),
        })
    return buckets


def today_kst():
    return datetime.now(KST).strftime("%Y-%m-%d")


def build_payload(buckets, date):
    return {"date": date, "buckets": buckets}


def call_openai(system_prompt, user_json, api_key, timeout=60):
    body = json.dumps({
        "model": MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content":
                "다음은 오늘의 수집 데이터(JSON)다. 이 buckets 만 근거로 브리핑을 작성하라.\n\n"
                + json.dumps(user_json, ensure_ascii=False)},
        ],
        "temperature": 0.4,
    }).encode("utf-8")
    req = urllib.request.Request(
        OPENAI_BASE + "/chat/completions", data=body,
        headers={"Authorization": "Bearer " + api_key,
                 "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"].strip()


def split_for_discord(text, limit=DISCORD_LIMIT):
    """줄 경계 기준으로 limit 이하 청크들로 분할."""
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            chunks.append(cur.rstrip())
            cur = ""
        # 한 줄이 limit 을 넘는 극단 케이스는 강제로 잘라 담는다.
        while len(line) > limit:
            chunks.append(line[:limit])
            line = line[limit:]
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur.rstrip())
    return chunks


def send_discord(webhook_url, text, timeout=30):
    for chunk in split_for_discord(text):
        body = json.dumps({"content": chunk}).encode("utf-8")
        req = urllib.request.Request(webhook_url, data=body,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status not in (200, 204):
                raise RuntimeError("Discord webhook 응답 %s" % resp.status)


def mark_sent(items):
    sys.path.insert(0, SCRIPTS_DIR)
    import sent_store  # noqa: E402
    return sent_store.mark_sent(items)


def main(argv=None):
    ap = argparse.ArgumentParser(description="브리핑 생성→Discord 전송→발송기록")
    ap.add_argument("--days", type=int, default=3, help="최근 N일(기본 3)")
    ap.add_argument("--top", type=int, default=8, help="상위 K개(기본 8, 카테고리 분할 고려)")
    ap.add_argument("--dry-run", action="store_true",
                    help="오프라인: 수집 샘플로 버킷/프롬프트만 확인(요약·전송·기록 없음)")
    ap.add_argument("--no-send", action="store_true",
                    help="요약까지 하되 Discord 전송/발송기록은 생략(콘솔 출력)")
    args = ap.parse_args(argv)

    items = run_collector(args.days, args.top, args.dry_run)
    buckets = bucketize(items)
    payload = build_payload(buckets, today_kst())
    counts = {k: len(v) for k, v in buckets.items()}
    log("[briefing] 버킷 — 핵심AI %d · Java·Spring %d · 기타 %d (총 %d)"
        % (counts["core_ai"], counts["java_spring"], counts["etc"], len(items)))

    with open(PROMPT_FILE, "r", encoding="utf-8") as f:
        system_prompt = f.read()

    # --dry-run: OpenAI 미호출. 어떤 데이터가 어떤 섹션으로 들어가는지 확인용.
    if args.dry_run:
        print("=== [dry-run] 브리핑 입력(buckets) ===")
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        print("\n=== 이 데이터가 위 4개 섹션(핵심 AI/Java·Spring/기타/아이디어)으로 요약됩니다 ===")
        return 0

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        log("[error] OPENAI_API_KEY 가 없습니다. (오프라인 확인은 --dry-run)")
        return 2

    try:
        briefing = call_openai(system_prompt, payload, api_key)
    except (urllib.error.URLError, urllib.error.HTTPError, KeyError, ValueError, TimeoutError) as e:
        log("[error] 브리핑 생성 실패: %s" % e)
        return 1

    webhook = os.environ.get("DISCORD_WEBHOOK_URL")
    if args.no_send or not webhook:
        if not webhook and not args.no_send:
            log("[warn] DISCORD_WEBHOOK_URL 없음 → 전송 대신 콘솔 출력(발송기록 생략)")
        print(briefing)
        return 0

    try:
        send_discord(webhook, briefing)
    except (urllib.error.URLError, urllib.error.HTTPError, RuntimeError, TimeoutError) as e:
        log("[error] Discord 전송 실패: %s (발송기록 생략 → 다음 실행에서 재시도)" % e)
        return 1

    # 전송 성공 후에만 기록(실패 시 재시도 가능하게)
    n = mark_sent(items)
    log("[done] Discord 전송 완료 · 발송기록 %d건 저장" % n)
    return 0


if __name__ == "__main__":
    sys.exit(main())
