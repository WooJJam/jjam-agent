#!/usr/bin/env python3
"""OpenAI 토큰 사용량 기록/집계 모듈 (jjam-agent / cost-usage).

P1 스텁: 실제 OpenAI 호출부는 아직 없고, 이 모듈은 "얼마나 썼는지"를
SQLite(`data/assistant.db`)에 적재하고 집계하는 저장/조회 계층만 담당한다.
표준 라이브러리(sqlite3, os, datetime)만 사용한다.

import 해서 쓰는 것을 전제로 한다:
    from usage_db import init_db, record_usage, stats_today, stats_month

주의: est_cost_usd 는 로컬 단가표(PRICING) 기반 "예상 비용"이며,
OpenAI 실제 청구액과는 차이가 날 수 있다(무료 티어/할인/반올림/캐시 등).
"""

import datetime
import os
import sqlite3

# Asia/Seoul: zoneinfo(Windows tzdata) 의존 회피용 고정 오프셋
KST = datetime.timezone(datetime.timedelta(hours=9))

# 이 파일(scripts/usage_db.py) 기준 레포 루트 = scripts 의 부모
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DEFAULT_DB = os.path.join(_REPO_ROOT, "data", "assistant.db")


def db_path():
    """DB 경로. 환경변수 ASSISTANT_DB 우선, 없으면 레포 루트의 data/assistant.db."""
    return os.environ.get("ASSISTANT_DB") or _DEFAULT_DB


# ── 단가표 ────────────────────────────────────────────────────────────────
# 1K 토큰당 USD (입력/출력). jjam-agent 기본 모델은 gpt-5.6-luna.
# 이 프로젝트는 아직 실 모델 공개 단가가 없어 유사 세대 모델을 참고한 "추정치"다.
# 실제 단가가 확정되면 이 dict 만 갱신하면 된다. 미등록 모델은 "default" 적용.
PRICING = {
    "gpt-5.6-luna":      {"input": 0.0025, "output": 0.010},   # 기본 모델(추정)
    "gpt-5.6-luna-mini": {"input": 0.0004, "output": 0.0016},  # 경량(추정)
    "gpt-4o":            {"input": 0.0050, "output": 0.015},
    "gpt-4o-mini":       {"input": 0.00015, "output": 0.0006},
    "default":           {"input": 0.0025, "output": 0.010},   # 미등록 모델 fallback
}


def _price_for(model):
    return PRICING.get(model, PRICING["default"])


def estimate_cost(model, in_tok, out_tok):
    """모델/토큰수로 예상 비용(USD) 계산. 1K 토큰당 단가 기준."""
    p = _price_for(model)
    in_tok = in_tok or 0
    out_tok = out_tok or 0
    cost = (in_tok / 1000.0) * p["input"] + (out_tok / 1000.0) * p["output"]
    return round(cost, 6)


# ── 스키마/연결 ───────────────────────────────────────────────────────────
def _connect():
    path = db_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn=None):
    """token_usage 테이블 생성(IF NOT EXISTS). conn 미지정 시 자체 연결."""
    own = conn is None
    if own:
        conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS token_usage (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                ts            TEXT    NOT NULL,
                feature       TEXT,
                model         TEXT,
                input_tokens  INTEGER DEFAULT 0,
                output_tokens INTEGER DEFAULT 0,
                est_cost_usd  REAL    DEFAULT 0,
                latency_ms    INTEGER DEFAULT 0,
                success       INTEGER DEFAULT 1
            )
            """
        )
        conn.commit()
    finally:
        if own:
            conn.close()
    return conn if not own else None


def record_usage(feature, model, input_tokens, output_tokens,
                 latency_ms, success=True, conn=None):
    """사용량 1건 기록. 예상 비용을 계산해 함께 저장하고 새 row id 를 반환."""
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        ts = datetime.datetime.now(KST).isoformat()
        cost = estimate_cost(model, input_tokens, output_tokens)
        cur = conn.execute(
            """
            INSERT INTO token_usage
                (ts, feature, model, input_tokens, output_tokens,
                 est_cost_usd, latency_ms, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (ts, feature, model, int(input_tokens or 0), int(output_tokens or 0),
             cost, int(latency_ms or 0), 1 if success else 0),
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if own:
            conn.close()


# ── 집계 ──────────────────────────────────────────────────────────────────
def _today_prefix():
    return datetime.datetime.now(KST).strftime("%Y-%m-%d")


def _month_prefix():
    return datetime.datetime.now(KST).strftime("%Y-%m")


def _aggregate(where_prefix, conn=None):
    """ts LIKE prefix% 조건으로 합계 집계."""
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        row = conn.execute(
            """
            SELECT
                COUNT(*)                       AS calls,
                COALESCE(SUM(input_tokens), 0) AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(est_cost_usd), 0) AS est_cost_usd,
                COALESCE(SUM(success), 0)      AS successes
            FROM token_usage
            WHERE ts LIKE ?
            """,
            (where_prefix + "%",),
        ).fetchone()
        return {
            "period": where_prefix,
            "calls": row["calls"],
            "successes": row["successes"],
            "input_tokens": row["input_tokens"],
            "output_tokens": row["output_tokens"],
            "est_cost_usd": round(row["est_cost_usd"], 6),
        }
    finally:
        if own:
            conn.close()


def stats_today(conn=None):
    """오늘(KST) 사용량 요약."""
    return _aggregate(_today_prefix(), conn=conn)


def stats_month(conn=None):
    """이번 달(KST) 사용량 요약."""
    return _aggregate(_month_prefix(), conn=conn)


def stats_by_feature(period="today", conn=None):
    """기능(feature)별 집계. period 는 'today' | 'month'.

    반환: {'period': <prefix>, 'features': [ {feature, calls, input_tokens,
           output_tokens, est_cost_usd}, ... ]} — 예상비용 내림차순 정렬.
    """
    prefix = _today_prefix() if period == "today" else _month_prefix()
    own = conn is None
    if own:
        conn = _connect()
    try:
        init_db(conn)
        rows = conn.execute(
            """
            SELECT
                COALESCE(feature, '(unknown)')  AS feature,
                COUNT(*)                        AS calls,
                COALESCE(SUM(input_tokens), 0)  AS input_tokens,
                COALESCE(SUM(output_tokens), 0) AS output_tokens,
                COALESCE(SUM(est_cost_usd), 0)  AS est_cost_usd
            FROM token_usage
            WHERE ts LIKE ?
            GROUP BY COALESCE(feature, '(unknown)')
            ORDER BY est_cost_usd DESC
            """,
            (prefix + "%",),
        ).fetchall()
        features = [
            {
                "feature": r["feature"],
                "calls": r["calls"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "est_cost_usd": round(r["est_cost_usd"], 6),
            }
            for r in rows
        ]
        return {"period": prefix, "features": features}
    finally:
        if own:
            conn.close()
