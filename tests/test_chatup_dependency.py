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

    assert '"chatup>=0.2.4,<0.3.0"' in pyproject
    assert '"chatbrowser>=0.1.2,<0.2.0"' in pyproject
    assert '"playwright>=1.50,<2.0"' in pyproject
    assert '"chatstyle>=0.1.1,<0.2.0"' in pyproject
    assert '"tomli>=2.0; python_version < \'3.11\'"' in pyproject
    chatup_version = tuple(int(part) for part in version("chatup").split("."))
    chatbrowser_version = tuple(int(part) for part in version("chatbrowser").split("."))
    playwright_version = tuple(int(part) for part in version("playwright").split("."))
    chatstyle_version = tuple(int(part) for part in version("chatstyle").split("."))
    assert (0, 2, 4) <= chatup_version < (0, 3, 0)
    assert (0, 1, 2) <= chatbrowser_version < (0, 2, 0)
    assert (1, 50, 0) <= playwright_version < (2, 0, 0)
    assert (0, 1, 1) <= chatstyle_version < (0, 2, 0)


def test_chatup_public_playwright_resolution_api_is_available():
    assert callable(resolve)
    assert PlaywrightBrowserInstallation.__name__ == "PlaywrightBrowserInstallation"
    assert DEFAULT_HOME.name == "playwright"
