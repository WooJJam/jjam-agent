#!/usr/bin/env python3
"""이미 브리핑으로 전송한 항목을 영구 기록해 '중복 발송'을 막는 저장소.

문제: 3일 필터 + 매일 수집이면, 같은 글이 3일 내내 다시 수집되어 매일 발송된다.
해결: 발송 성공한 항목의 (정규화) URL 을 SQLite 에 기록하고,
      collect-news.py 가 다음 수집 때 '이미 보낸 것'을 제외한다.

- 저장: data/assistant.db (ASSISTANT_DB 로 override) 의 sent_items 테이블
- collect-news.py : already_sent(url_norms) 로 제외 대상 조회
- make-briefing.py: 전송 성공 후 mark_sent(items) 로 기록
- 표준 라이브러리(sqlite3)만 사용.

CLI:
    python3 scripts/sent_store.py list
    python3 scripts/sent_store.py mark   < collector_output.json   # 발송 항목 기록
    python3 scripts/sent_store.py prune --days 30                  # 오래된 기록 정리
"""

import argparse
import datetime
import json
import os
import sqlite3
import sys

KST = datetime.timezone(datetime.timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_ROOT, "data", "assistant.db")


def db_path():
    return os.environ.get("ASSISTANT_DB") or _DEFAULT_DB


def _connect():
    p = db_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn=None):
    own = conn is None
    if own:
        conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sent_items (
                url_norm   TEXT PRIMARY KEY,
                title      TEXT,
                source_id  TEXT,
                sent_at    TEXT NOT NULL
            )
            """
        )
        conn.commit()
    finally:
        if own:
            conn.close()


def already_sent(url_norms, conn=None):
    """주어진 정규화 URL 중 '이미 보낸' 것들의 집합을 반환."""
    urls = [u for u in url_norms if u]
    if not urls:
        return set()
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        found = set()
        for i in range(0, len(urls), 400):  # SQLite 변수 한도 회피
            chunk = urls[i:i + 400]
            q = "SELECT url_norm FROM sent_items WHERE url_norm IN (%s)" % ",".join("?" * len(chunk))
            found.update(r["url_norm"] for r in conn.execute(q, chunk).fetchall())
        return found
    finally:
        if own:
            conn.close()


def mark_sent(items, conn=None):
    """발송 완료 항목 기록. items: [{url_norm, title, source_id}]. 중복은 무시. 새로 기록된 수 반환."""
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        ts = datetime.datetime.now(KST).isoformat()
        n = 0
        for it in items:
            u = it.get("url_norm")
            if not u:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO sent_items (url_norm, title, source_id, sent_at) VALUES (?, ?, ?, ?)",
                (u, it.get("title"), it.get("source_id"), ts),
            )
            n += cur.rowcount
        conn.commit()
        return n
    finally:
        if own:
            conn.close()


def prune(days=30, conn=None):
    """days 보다 오래된 기록 삭제(저장소 비대화 방지). 삭제 수 반환."""
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        cutoff = (datetime.datetime.now(KST) - datetime.timedelta(days=days)).isoformat()
        cur = conn.execute("DELETE FROM sent_items WHERE sent_at < ?", (cutoff,))
        conn.commit()
        return cur.rowcount
    finally:
        if own:
            conn.close()


def main(argv=None):
    ap = argparse.ArgumentParser(description="브리핑 전송 항목 기록(중복 발송 방지)")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("list", help="최근 기록 표시")
    sub.add_parser("mark", help="stdin 의 collector JSON 배열을 '보냄'으로 기록")
    p = sub.add_parser("prune", help="오래된 기록 삭제")
    p.add_argument("--days", type=int, default=30)
    args = ap.parse_args(argv)

    if args.cmd == "mark":
        items = json.load(sys.stdin)
        if not isinstance(items, list):
            sys.stderr.write("입력은 항목 JSON 배열이어야 합니다.\n")
            return 1
        print("기록 %d건(중복 제외)" % mark_sent(items))
        return 0

    if args.cmd == "prune":
        print("삭제 %d건" % prune(args.days))
        return 0

    # 기본: list
    conn = _connect()
    init_db(conn)
    rows = conn.execute(
        "SELECT url_norm, title, source_id, sent_at FROM sent_items ORDER BY sent_at DESC LIMIT 50"
    ).fetchall()
    for r in rows:
        print("  %s  %-50s [%s]" % (r["sent_at"][:19], (r["title"] or "")[:50], r["source_id"]))
    total = conn.execute("SELECT COUNT(*) AS c FROM sent_items").fetchone()["c"]
    print("총 %d건 (최근 50건 표시)" % total)
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
