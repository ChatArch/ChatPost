from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


LOGIN_COMMANDS = (
    "chatpost --tree",
    "chatpost platforms",
    "chatpost profiles",
    "chatpost zhihu profiles",
    "chatpost zhihu login",
    "chatpost zhihu status",
    "chatpost zhihu logout",
)

FORBIDDEN_LOGIN_SURFACE = (
    "chatpost account",
    "chatpost qr",
    "chatpost zhihu account",
    "chatpost zhihu draft",
    "qr-artifact",
    "--qr",
    "--receipt",
    "WECHATSYNC_TOKEN",
    "auth zhihu",
)


def test_cli_tree_documents_login_only_registered_surface():
    for relative in ("docs/cli-tree.md", "docs/cli-tree.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for command in LOGIN_COMMANDS:
            assert command in text
        for forbidden in FORBIDDEN_LOGIN_SURFACE:
            assert forbidden not in text
        assert "browser-level" in text or "浏览器" in text
        assert "page-owned `login_url`" in text
        assert "LOGGED_IN" in text
        assert "LOGGED_OUT" in text
        assert "UNKNOWN" in text
        assert "Cookie" in text or "cookies" in text
        assert "LocalStorage" in text or "local storage" in text
        assert "IndexedDB" in text
        assert "session" in text
        assert "token" in text


def test_quickstart_is_login_only_and_keeps_adapter_boundary_out():
    for relative in ("docs/quickstart.md", "docs/quickstart.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for command in LOGIN_COMMANDS:
            if command == "chatpost --tree":
                continue
            assert command in text
        for forbidden in FORBIDDEN_LOGIN_SURFACE:
            assert forbidden not in text
        assert "JSON Lines" in text
        assert "page-owned `login_url`" in text
        assert "browser_opened" in text
        assert "LOGGED_IN" in text
        assert "LOGGED_OUT" in text
        assert "UNKNOWN" in text
        assert "--phone" in text
        assert "--sms-code" in text
        assert "Cookie" in text or "cookies" in text
        assert "LocalStorage" in text or "local storage" in text
        assert "IndexedDB" in text


def test_home_readme_and_mkdocs_route_to_login_quickstart():
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "快速开始: quickstart.md" in mkdocs
    assert "快速开始: Quickstart" in mkdocs

    zh_home = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    en_home = (ROOT / "docs/index.en.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    en_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "Quickstart：纯浏览器登录" in zh_home
    assert "Quickstart: Pure Browser Login" in en_home
    assert "Quickstart：纯浏览器登录" in zh_readme
    assert "Quickstart: Pure Browser Login" in en_readme
    for text in (zh_home, en_home, zh_readme, en_readme):
        assert "chatpost zhihu login" in text or "login/status/logout" in text
        assert "chatpost zhihu draft" not in text
        assert "WECHATSYNC_TOKEN" not in text


def test_capability_map_says_browser_login_does_not_touch_adapter():
    text = (ROOT / "docs/capability-map.md").read_text(encoding="utf-8")
    assert "知乎纯浏览器登录/状态/登出" in text
    assert "不调用发布适配器" in text
    assert "不加载发布扩展" in text
    assert "不要求发布 token" in text
    assert "load_browser_config" in text
    assert "--load-extension" in text
    assert "chatpost zhihu draft" in text
    assert "不在当前登录基础层" in text
