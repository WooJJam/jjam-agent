"""secret_scan.py 단위 테스트.

주의: 테스트의 '시크릿'은 전부 실존하지 않는 더미 문자열이다.
"""
import contextlib
import io
import json
import sys
import unittest

from _load import load_hook

ss = load_hook("secret_scan")

# 실존하지 않는 더미 토큰 (형식만 실제와 동일).
# 소스/diff에 완성된 패턴이 남지 않도록 런타임 조립한다 —
# 이 파일 자체가 시크릿 스캐너(커밋 훅·PR 검사)에 걸리지 않게 하기 위함.
FAKE_OPENAI = "sk-" + "Ab3dEfGh1jKlMnOpQrStUvWx"
FAKE_GH = "ghp_" + "Ab3dEfGh1jKlMnOpQrStUvWx0123"
FAKE_AWS = "AKIA" + "ABCDEFGHIJKL"
FAKE_DISCORD = ".".join(["MTA5MjY1NTAxNzc4NjQ0OTkzNx", "G7abcd",
                         "mnopqrstuvwxyz0123456789ABCDE"])
FAKE_JWT = ".".join(["eyJhbGciOiJIUzI1NiJ9", "eyJzdWIiOiIxMjM0NTY3ODkwIn0"])
FAKE_PRIVKEY = "-----BEGIN RSA PRIVATE " + "KEY-----"


class TestFindSecrets(unittest.TestCase):
    def test_detects_each_known_format(self):
        cases = {
            "OpenAI": FAKE_OPENAI,
            "GitHub": FAKE_GH,
            "AWS": FAKE_AWS,
            "Discord": FAKE_DISCORD,
            "JWT": FAKE_JWT,
            "개인키": FAKE_PRIVKEY,
        }
        for label, token in cases.items():
            with self.subTest(label=label):
                self.assertTrue(ss.find_secrets(f"이 값으로 설정: {token}"),
                                f"{label} 형식을 놓침")

    def test_detects_assignment_context(self):
        self.assertTrue(ss.find_secrets("API_KEY=" + "Qw3rTy9uIoPa5sDf7gHjKl1z"))
        self.assertTrue(ss.find_secrets("password: " + '"Zx9KqW3rTy8uIoPa5sDf7g"'))

    def test_short_sk_passes(self):
        # 실제 키로 존재할 수 없는 길이(16자 미만)는 통과
        self.assertFalse(ss.find_secrets("sk-1234AASXV 로 수정"))

    def test_prose_mention_passes(self):
        self.assertFalse(ss.find_secrets("sk- 패턴이 뭐냐면, OpenAI 키 형식이야"))

    def test_placeholder_passes(self):
        self.assertFalse(ss.find_secrets("문서에 sk-xxxxxxxxxxxxxxxxxxxx 라고 써줘"))
        self.assertFalse(ss.find_secrets("TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx"))
        self.assertFalse(ss.find_secrets("KEY=************************"))

    def test_short_assignment_value_passes(self):
        # 할당문이어도 값이 20자 미만이면 통과 (일반 설정값 오탐 방지)
        self.assertFalse(ss.find_secrets("WEATHER_API_KEY=abc123"))


class TestIsPlaceholder(unittest.TestCase):
    def test_placeholders(self):
        for text in ["sk-xxxxxxxxxxxxxxxxxxxx", "aaaaaaaaaaaaaaaaaaaa",
                     "sk-xXxXxXxXxXxXxXxXxX", "****************"]:
            with self.subTest(text=text):
                self.assertTrue(ss.is_placeholder(text))

    def test_real_shaped_value_is_not_placeholder(self):
        self.assertFalse(ss.is_placeholder(FAKE_OPENAI))


class TestCheckDanger(unittest.TestCase):
    def _run(self, command: str):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ss.check_danger(command)
        out = buf.getvalue().strip()
        decision = None
        if out:
            decision = json.loads(out)["hookSpecificOutput"]["permissionDecision"]
        return rc, decision

    def test_force_push_direct_asks(self):
        self.assertEqual(self._run("git push --force origin main"), (0, "ask"))

    def test_force_push_in_compound_asks(self):
        self.assertEqual(
            self._run("cd scripts && git push --force origin main"), (0, "ask"))

    def test_force_push_short_flag_asks(self):
        self.assertEqual(self._run("git push -f origin main"), (0, "ask"))

    def test_reset_hard_asks(self):
        self.assertEqual(self._run("git reset --hard HEAD~1"), (0, "ask"))

    def test_terraform_apply_denied(self):
        self.assertEqual(self._run("cd infra; terraform apply"), (0, "deny"))

    def test_terraform_destroy_denied(self):
        self.assertEqual(self._run("terraform destroy -auto-approve"), (0, "deny"))

    def test_quoted_mention_ignored(self):
        rc, decision = self._run('git commit -m "docs: terraform apply 절차 설명"')
        self.assertEqual((rc, decision), (-1, None))

    def test_plain_commands_ignored(self):
        for cmd in ["git status", "git push origin main", "terraform plan", "ls -la"]:
            with self.subTest(cmd=cmd):
                self.assertEqual(self._run(cmd), (-1, None))


class TestForbiddenStagedPattern(unittest.TestCase):
    def test_blocked_filenames(self):
        for name in [".env", "config/.env", ".env.local", "data/assistant.db",
                     "가계부.xlsx", "backup.db", "server.pem", "id_rsa.key"]:
            with self.subTest(name=name):
                self.assertTrue(ss.FORBIDDEN_STAGED.search(name), f"{name} 놓침")

    def test_allowed_filenames(self):
        for name in [".env.example", "scripts/finance_db.py", "docs/FINANCE_SPEC.md",
                     "config/hermes.yaml", "environment.md"]:
            with self.subTest(name=name):
                self.assertFalse(ss.FORBIDDEN_STAGED.search(name), f"{name} 오탐")


class TestModePrompt(unittest.TestCase):
    def _run(self, prompt: str):
        stdin, sys.stdin = sys.stdin, io.StringIO(json.dumps({"prompt": prompt}))
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = ss.mode_prompt()
        finally:
            sys.stdin = stdin
        return rc, buf.getvalue().strip()

    def test_secret_input_blocked(self):
        rc, out = self._run(f"이 키로 설정해줘 {FAKE_OPENAI}")
        self.assertEqual(rc, 0)
        self.assertEqual(json.loads(out)["decision"], "block")

    def test_clean_input_passes(self):
        rc, out = self._run("날씨 스크립트 고쳐줘")
        self.assertEqual((rc, out), (0, ""))


if __name__ == "__main__":
    unittest.main()
