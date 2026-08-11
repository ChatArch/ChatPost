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
    "chatpost zhihu draft",
    "chatpost xhs profiles",
    "chatpost xhs login",
    "chatpost xhs status",
    "chatpost xhs logout",
)

FORBIDDEN_LOGIN_SURFACE = (
    "chatpost account",
    "chatpost qr",
    "chatpost zhihu account",
    "chatpost xhs draft",
    "qr-artifact",
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
        assert "--qrcode PATH" in text
        assert "qrcode_path" in text
        assert "LOGGED_IN" in text
        assert "LOGGED_OUT" in text
        assert "UNKNOWN" in text
        assert "Cookie" in text or "cookies" in text
        assert "LocalStorage" in text or "local storage" in text
        assert "IndexedDB" in text
        assert "session" in text
        assert "token" in text


def test_quickstart_covers_login_and_draft_while_preserving_login_boundary():
    for relative in ("docs/quickstart.md", "docs/quickstart.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for command in LOGIN_COMMANDS:
            if command == "chatpost --tree":
                continue
            assert command in text
        for forbidden in FORBIDDEN_LOGIN_SURFACE:
            assert forbidden not in text
        assert "JSON Lines" in text
        assert "~/.chatarch/chatpost" in text
        assert "CHATPOST_ACCOUNT_REGISTRY" in text
        assert "page-owned `login_url`" in text
        assert "--qrcode" in text
        assert "qrcode_path" in text
        assert "--dry-run" in text
        assert "--receipt" in text
        assert "pip install ChatPost" in text
        assert "ChatUp" in text
        assert "ChatBrowser" in text
        assert "ChatPost" in text
        assert "chatup playwright install" in text
        assert "chatbrowser profile create" in text
        assert "browser_profile" in text
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
    assert "Quickstart：逻辑 Profile、知乎登录与草稿" in zh_home
    assert "Quickstart: Logical Profiles, Zhihu Login, and Drafts" in en_home
    assert "Quickstart：逻辑 Profile、知乎登录与草稿" in zh_readme
    assert "Quickstart: Logical Profiles, Zhihu Login, and Drafts" in en_readme
    for text in (zh_home, en_home, zh_readme, en_readme):
        assert "chatpost zhihu login" in text or "login/status/logout" in text
        assert "chatpost zhihu draft" in text
        assert "chatpost xhs draft" not in text
        assert "qrcode_path" in text
        assert "WECHATSYNC_TOKEN" not in text
    for text in (zh_home, en_home):
        assert "~/.chatarch/chatpost/accounts.toml" in text


def test_quickstart_uses_logical_profiles_without_live_identity_or_login_urls():
    text = (ROOT / "docs/quickstart.md").read_text(encoding="utf-8")
    for forbidden in (
        "致宏",
        "rexwzh",
        "people/40qok4",
        "people/rexwzh",
        "scan/login",
        "zhihu-personal",
        "xhs-personal",
        "zhihu-practice-quickstart",
    ):
        assert forbidden not in text
    assert "PROFILE=test" in text
    assert "profiles/" in text
    assert "product/" in text
    assert "当前不作为验收主线" in text


def test_interface_tree_documents_default_state_root_and_browser_api():
    for relative in ("docs/interface-tree.md", "docs/interface-tree.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "default_chatpost_home()" in text
        assert "default_registry_path()" in text
        assert "~/.chatarch/chatpost" in text
        assert "load_browser_config(path)" in text
        assert "browser_profile" in text
        assert "chatbrowser.registry.profile_path" in text
        assert "browser_status(config)" in text
        assert "browser_login(config" in text
        assert "browser_logout(config)" in text
        assert "load_runner_config(path)" in text
        assert "Wechatsync" in text


def test_configuration_documents_default_state_root_and_current_registry_shape():
    for relative in ("docs/configuration.md", "docs/configuration.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "~/.chatarch/chatpost/accounts.toml" in text
        assert "CHATPOST_HOME" in text
        assert "CHATPOST_ACCOUNT_REGISTRY" in text
        assert "runner_config = \"runners/zhihu-personal/runner.toml\"" in text
        assert "LocalStorage" in text or "local storage" in text
        assert "IndexedDB" in text


def test_capability_map_says_browser_login_does_not_touch_adapter():
    zh_text = (ROOT / "docs/capability-map.md").read_text(encoding="utf-8")
    en_text = (ROOT / "docs/capability-map.en.md").read_text(encoding="utf-8")
    assert "知乎纯浏览器登录/状态/登出" in zh_text
    assert "小红书二维码登录/状态/登出" in zh_text
    assert "不调用发布适配器" in zh_text
    assert "不加载发布扩展" in zh_text
    assert "不要求发布 token" in zh_text
    assert "load_browser_config" in zh_text
    assert "--load-extension" in zh_text
    assert "chatpost zhihu draft" in zh_text
    assert "不在 login/status/logout 登录基础层" in zh_text
    assert "已实现" in zh_text
    for text in (zh_text, en_text):
        assert "~/.chatarch/chatpost" in text
        assert "ChatArch state root" in text or "ChatArch state root" in en_text
        assert "load_browser_config" in text
        assert "chatpost zhihu draft" in text
        assert "chatpost xhs draft/create" in text
        assert "qrcode_path" in text
        assert "Wechatsync" in text
