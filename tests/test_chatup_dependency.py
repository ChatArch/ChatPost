from importlib.metadata import version
from pathlib import Path

from chatup.playwright import (
    DEFAULT_HOME,
    PlaywrightBrowserInstallation,
    resolve,
)

ROOT = Path(__file__).resolve().parents[1]


def test_chatpost_uses_bounded_published_chatarch_dependencies():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"chatup>=0.2.12,<0.3.0"' in pyproject
    assert '"chatbrowser>=0.1.5,<0.2.0"' in pyproject
    assert '"chatstyle>=0.2.0,<0.3.0"' in pyproject
    assert '"chatenv>=0.2.10,<0.3.0"' in pyproject
    assert '"tomli>=2.0; python_version < \'3.11\'"' in pyproject
    chatup_version = tuple(int(part) for part in version("chatup").split("."))
    chatbrowser_version = tuple(int(part) for part in version("chatbrowser").split("."))
    chatstyle_version = tuple(int(part) for part in version("chatstyle").split("."))
    chatenv_version = tuple(int(part) for part in version("chatenv").split("."))
    assert (0, 2, 12) <= chatup_version < (0, 3, 0)
    assert (0, 1, 5) <= chatbrowser_version < (0, 2, 0)
    assert (0, 2, 0) <= chatstyle_version < (0, 3, 0)
    assert (0, 2, 10) <= chatenv_version < (0, 3, 0)


def test_chatup_public_playwright_resolution_api_is_available():
    assert callable(resolve)
    assert PlaywrightBrowserInstallation.__name__ == "PlaywrightBrowserInstallation"
    assert DEFAULT_HOME.name == "playwright"
