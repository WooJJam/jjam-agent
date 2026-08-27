"""GitHub 이슈 생성 (gh CLI 부재 환경용).

토큰은 git credential helper에서 조회하며 어디에도 출력하지 않는다.
사용:
  py .claude/skills/open-issue/create_issue.py \
     --title "[feat] 제목" --body-file body.md --labels "feat,finance"
출력: "ISSUE <번호> <URL>" 한 줄 (파싱용).
"""
import argparse
import json
import subprocess
import sys
import urllib.request

REPO = "WooJJam/jjam-agent"
VALID_TYPE_LABELS = {"feat", "fix", "docs", "infra", "chore"}


def get_token() -> str:
    out = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n",
        capture_output=True, text=True, check=True,
    ).stdout
    for line in out.splitlines():
        if line.startswith("password="):
            return line.split("=", 1)[1]
    sys.exit("git credential에서 토큰을 찾지 못했습니다.")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--title", required=True)
    ap.add_argument("--body-file", required=True)
    ap.add_argument("--labels", required=True, help="쉼표 구분, 첫 라벨은 타입")
    args = ap.parse_args()

    labels = [l.strip() for l in args.labels.split(",") if l.strip()]
    if not labels or labels[0] not in VALID_TYPE_LABELS:
        sys.exit(f"첫 라벨은 타입({'|'.join(sorted(VALID_TYPE_LABELS))})이어야 합니다: {labels}")
    prefix = f"[{labels[0]}] "
    if not args.title.startswith(prefix):
        sys.exit(f"제목은 '{prefix}'로 시작해야 합니다: {args.title}")
    if len(args.title) <= len(prefix) + 2:
        sys.exit("제목 요약이 너무 짧습니다.")

    with open(args.body_file, encoding="utf-8") as f:
        body = f.read().strip()
    if not body:
        sys.exit("본문이 비어 있습니다.")

    req = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/issues",
        data=json.dumps({"title": args.title, "body": body, "labels": labels}).encode(),
        headers={
            "Authorization": "token " + get_token(),
            "Accept": "application/vnd.github+json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            r = json.load(resp)
    except urllib.error.HTTPError as e:
        sys.exit(f"이슈 생성 실패 HTTP {e.code}: {e.read().decode()[:300]}")
    print(f"ISSUE {r['number']} {r['html_url']}")


if __name__ == "__main__":
    main()
