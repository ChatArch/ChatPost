import importlib.util
from importlib.metadata import version
from pathlib import Path

from chatup.chrome_for_testing import (
    ChromeForTestingInstallation,
    DEFAULT_HOME,
    resolve,
)


ROOT = Path(__file__).resolve().parents[1]


def test_chatpost_uses_bounded_published_chatup_and_chatstyle_dependencies():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert '"chatup>=0.2.3,<0.3.0"' in pyproject
    assert '"chatstyle>=0.1.1,<0.2.0"' in pyproject
    chatup_version = tuple(int(part) for part in version("chatup").split("."))
    chatstyle_version = tuple(int(part) for part in version("chatstyle").split("."))
    assert (0, 2, 3) <= chatup_version < (0, 3, 0)
    assert (0, 1, 1) <= chatstyle_version < (0, 2, 0)


def test_chatup_public_cft_resolution_api_is_available_without_legacy_alias():
    assert callable(resolve)
    assert ChromeForTestingInstallation.__name__ == "ChromeForTestingInstallation"
    assert DEFAULT_HOME.name == "chrome-for-testing"
    assert importlib.util.find_spec("chatup.chrome") is None
