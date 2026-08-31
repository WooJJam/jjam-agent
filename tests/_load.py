"""테스트 공용 헬퍼 — .claude/hooks/ 아래 모듈을 importlib으로 로드한다.

(디렉터리명에 점이 있어 일반 import 불가)
실행: py -m unittest discover -s tests -v
"""
import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_hook(name: str):
    path = REPO_ROOT / ".claude" / "hooks" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
