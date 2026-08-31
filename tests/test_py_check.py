"""py_check.py (PostToolUse 문법 검증 훅) 단위 테스트."""
import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from _load import load_hook

pc = load_hook("py_check")


def run_main(payload: dict) -> int:
    stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps(payload))
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            return pc.main()
    finally:
        sys.stdin = stdin


class TestPyCheck(unittest.TestCase):
    def test_valid_python_passes(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "ok.py"
            f.write_text("x = 1\n", encoding="utf-8")
            self.assertEqual(
                run_main({"tool_input": {"file_path": str(f)}}), 0)

    def test_broken_python_exits_2(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "broken.py"
            f.write_text("def broken(:\n", encoding="utf-8")
            self.assertEqual(
                run_main({"tool_input": {"file_path": str(f)}}), 2)

    def test_non_python_ignored(self):
        self.assertEqual(
            run_main({"tool_input": {"file_path": "README.md"}}), 0)

    def test_missing_file_ignored(self):
        self.assertEqual(
            run_main({"tool_input": {"file_path": "없는파일.py"}}), 0)

    def test_bad_stdin_ignored(self):
        stdin, sys.stdin = sys.stdin, io.StringIO("이건 JSON이 아님")
        try:
            self.assertEqual(pc.main(), 0)
        finally:
            sys.stdin = stdin


if __name__ == "__main__":
    unittest.main()
