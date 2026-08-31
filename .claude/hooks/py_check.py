"""PostToolUse 훅: Write/Edit된 .py 파일을 py_compile로 즉시 문법 검증.

실패 시 exit 2 → stderr가 Claude에게 전달되어 즉시 수정하게 한다.
.py 외 파일은 무시(exit 0).
"""
import json
import py_compile
import sys


def main() -> int:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0
    file_path = (data.get("tool_input") or {}).get("file_path", "")
    if not file_path.endswith(".py"):
        return 0
    try:
        py_compile.compile(file_path, doraise=True)
    except FileNotFoundError:
        return 0
    except py_compile.PyCompileError as e:
        print(f"[py_check] 문법 오류: {e}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
