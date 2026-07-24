#!/usr/bin/env python3
"""OpenAI 토큰 사용량 요약 CLI (jjam-agent / cost-usage).

usage_db 모듈을 import 해 오늘/이번달 사용량을 사람이 읽기 쉬운 형태로 출력한다.
예상 비용은 로컬 단가표 기반이라 항상 "예상" 라벨을 붙인다.

사용 예:
    py scripts/get-token-usage.py --seed     # 더미 데이터 삽입(테스트용)
    py scripts/get-token-usage.py today
    py scripts/get-token-usage.py month
    py scripts/get-token-usage.py today --feature   # 기능별 분해
    py scripts/get-token-usage.py month --json      # 기계용 JSON
"""

import argparse
import datetime
import json
import os
import sys

# 같은 폴더의 usage_db 를 import 가능하게 (단독 실행 대비)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_db  # noqa: E402


def _seed():
    """다양한 기능/모델의 더미 사용량을 삽입해 통계 출력을 테스트한다.

    오늘 기록 + 이번달(과거 날짜) 기록을 섞어 today/month 차이를 확인할 수 있게 한다.
    """
    conn = usage_db._connect()
    try:
        usage_db.init_db(conn)
        now = datetime.datetime.now(usage_db.KST)
        samples = [
            # (feature, model, in_tok, out_tok, latency_ms, success, day_offset)
            ("chat",     "gpt-5.6-luna",      1200,  800, 1400, True, 0),
            ("chat",     "gpt-5.6-luna",      900,   500, 1100, True, 0),
            ("weather",  "gpt-5.6-luna-mini", 300,   120, 450,  True, 0),
            ("summary",  "gpt-5.6-luna",      4000, 1500, 2600, True, 0),
            ("summary",  "gpt-5.6-luna",      3800, 1400, 2500, False, 0),
            ("chat",     "gpt-5.6-luna",      1000,  600, 1200, True, 3),
            ("weather",  "gpt-5.6-luna-mini", 280,   100, 400,  True, 5),
        ]
        for feature, model, in_tok, out_tok, latency, ok, off in samples:
            ts = (now - datetime.timedelta(days=off)).isoformat()
            cost = usage_db.estimate_cost(model, in_tok, out_tok)
            conn.execute(
                """
                INSERT INTO token_usage
                    (ts, feature, model, input_tokens, output_tokens,
                     est_cost_usd, latency_ms, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ts, feature, model, in_tok, out_tok, cost, latency, 1 if ok else 0),
            )
        conn.commit()
        return len(samples)
    finally:
        conn.close()


def _label(period):
    return "오늘" if period == "today" else "이번 달"


def format_text(period, summary, by_feature=None):
    lines = []
    lines.append("[토큰 사용량 요약] %s (%s, KST)" % (_label(period), summary["period"]))
    lines.append("- 호출 수: {:,}회 (성공 {:,})".format(
        summary["calls"], summary["successes"]))
    lines.append("- 입력 토큰: {:,}".format(summary["input_tokens"]))
    lines.append("- 출력 토큰: {:,}".format(summary["output_tokens"]))
    lines.append("- 합계 토큰: {:,}".format(
        summary["input_tokens"] + summary["output_tokens"]))
    lines.append("- 예상 비용: ${:.4f} (예상치 · 실제 청구액과 다를 수 있음)".format(
        summary["est_cost_usd"]))

    if by_feature is not None:
        lines.append("")
        lines.append("[기능별 분해]")
        if not by_feature["features"]:
            lines.append("- (데이터 없음)")
        for f in by_feature["features"]:
            lines.append(
                "- {:<10} 호출 {:>3}회 · in {:,} / out {:,} · 예상 ${:.4f}".format(
                    f["feature"], f["calls"], f["input_tokens"],
                    f["output_tokens"], f["est_cost_usd"])
            )
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OpenAI 토큰 사용량 요약 (jjam-agent)")
    parser.add_argument("period", nargs="?", default="today",
                        choices=["today", "month"],
                        help="집계 기간 (기본: today)")
    parser.add_argument("--feature", action="store_true",
                        help="기능(feature)별로 분해해 표시")
    parser.add_argument("--seed", action="store_true",
                        help="더미 사용량 데이터를 삽입(테스트용) 후 종료")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="JSON으로 출력(기계용)")
    args = parser.parse_args(argv)

    usage_db.init_db()

    if args.seed:
        n = _seed()
        print("더미 사용량 %d건을 %s 에 삽입했습니다." % (n, usage_db.db_path()))
        return 0

    if args.period == "today":
        summary = usage_db.stats_today()
    else:
        summary = usage_db.stats_month()

    by_feature = usage_db.stats_by_feature(args.period) if args.feature else None

    if args.as_json:
        out = {"summary": summary}
        if by_feature is not None:
            out["by_feature"] = by_feature
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(format_text(args.period, summary, by_feature))
    return 0


if __name__ == "__main__":
    sys.exit(main())
