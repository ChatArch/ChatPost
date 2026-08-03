from importlib.metadata import version
from pathlib import Path

from chatup.chrome import ensure_chrome, resolve_chrome

ROOT = Path(__file__).resolve().parents[1]


def test_chatpost_uses_bounded_published_chatup_dependency():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"chatup>=0.2.2,<0.3.0"' in pyproject
    installed = tuple(int(part) for part in version("chatup").split("."))
    assert (0, 2, 2) <= installed < (0, 3, 0)


def test_chatup_public_chrome_resolution_api_is_available():
    assert callable(resolve_chrome)
    assert callable(ensure_chrome)
