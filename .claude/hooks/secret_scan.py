"""시크릿 노출 방지 통합 스캐너 (#17).

두 하네스 훅이 모드만 다르게 호출한다:
- --prompt  : UserPromptSubmit 훅. 사용자 입력에서 시크릿 패턴 검출 시
              모델 전송 전에 차단(JSON decision:block).
- --pretool : PreToolUse(Bash|PowerShell) 훅. 명령이 git commit이면
              스테이징 diff·파일명을 스캔, 검출 시 커밋 실행 차단(exit 2).

판별 기준: ①고정 형식(주요 서비스 토큰) ②보수적 문맥 매칭(할당문 + 긴 값).
플레이스홀더(xxxx…, ****, 문자 다양성 없음)는 오탐 방지를 위해 제외.
"""
import json
import re
import subprocess
import sys

SECRET_PATTERNS = [
    ("OpenAI API 키", re.compile(r"sk-[A-Za-z0-9_-]{16,}")),
    ("GitHub 토큰", re.compile(r"gh[pousr]_[A-Za-z0-9]{16,}|github_pat_[A-Za-z0-9_]{16,}")),
    ("AWS 액세스 키", re.compile(r"AKIA[A-Z0-9]{12,}")),
    ("개인키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Discord 토큰", re.compile(r"[MN][A-Za-z0-9_-]{23,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}")),
    ("JWT", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}")),
    ("할당문 시크릿", re.compile(
        r"(?i)(api[_-]?key|secret|token|passwd|password)\s*[=:]\s*[\"']?[A-Za-z0-9_\-+/]{20,}")),
]

FORBIDDEN_STAGED = re.compile(
    r"(^|/)\.env($|\.(?!example$))|\.xlsx$|(^|/)data/|\.db$|\.pem$|\.key$", re.IGNORECASE)


def is_placeholder(text: str) -> bool:
    """xxxx…, ****, aaaa… 같은 예시값은 시크릿이 아니다."""
    core = re.sub(r"[^A-Za-z0-9]", "", text)
    return len(set(core.lower())) <= 2 or "xxxx" in text.lower() or "****" in text


def find_secrets(text: str) -> list[str]:
    hits = []
    for name, pat in SECRET_PATTERNS:
        for m in pat.finditer(text):
            if not is_placeholder(m.group(0)):
                hits.append(name)
                break
    return hits


def mode_prompt() -> int:
    data = json.load(sys.stdin)
    hits = find_secrets(data.get("prompt", "") or "")
    if hits:
        print(json.dumps({
            "decision": "block",
            "reason": (
                f"입력에서 시크릿 패턴 검출: {', '.join(hits)}. "
                "이 메시지는 모델로 전송되지 않았습니다. 시크릿 값은 채팅에 넣지 말고 "
                "터미널에서 직접 입력하세요 (예: hermes config set KEY VALUE)."
            ),
        }, ensure_ascii=False))
    return 0


def mode_pretool() -> int:
    data = json.load(sys.stdin)
    command = (data.get("tool_input") or {}).get("command", "") or ""
    if "git commit" not in command:
        return 0

    staged_files = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True).stdout.splitlines()
    forbidden = [f for f in staged_files if FORBIDDEN_STAGED.search(f)]
    if forbidden:
        print("[secret_scan] 커밋 차단 — 금지 파일이 스테이징됨: "
              + ", ".join(forbidden), file=sys.stderr)
        return 2

    diff = subprocess.run(
        ["git", "diff", "--cached"],
        capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    added = "\n".join(l for l in diff.splitlines() if l.startswith("+"))
    hits = find_secrets(added)
    if hits:
        print("[secret_scan] 커밋 차단 — 스테이징된 변경에서 시크릿 패턴 검출: "
              + ", ".join(hits) + ". 해당 줄을 제거한 뒤 다시 커밋하세요.", file=sys.stderr)
        return 2
    return 0


def main() -> int:
    if "--prompt" in sys.argv:
        return mode_prompt()
    if "--pretool" in sys.argv:
        return mode_pretool()
    print("usage: secret_scan.py --prompt|--pretool", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
