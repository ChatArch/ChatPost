from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_tree_matches_registered_task_commands():
    for relative in ("docs/cli-tree.md", "docs/cli-tree.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for command in (
            "chatpost --tree",
            "chatpost platforms",
            "chatpost profiles",
            "chatpost zhihu profiles",
            "chatpost zhihu login",
            "chatpost zhihu logout",
            "chatpost zhihu status",
            "chatpost zhihu draft",
            "--dry-run",
        ):
            assert command in text
        assert "chatpost zhihu draft dry-run" not in text
        assert "chatpost zhihu draft create" not in text
        assert "Hidden compatibility" in text
        assert "chatpost zhihu account status/preflight/login qr/login qr-artifact/login code" in text
        assert "chatpost login --help" not in text
        assert "chatpost post --help" not in text
        assert "chatpost login qr-image" not in text
        assert "chatpost post draft" not in text
        assert "chatup playwright install 1.61.1" in text
        assert "chatup.playwright" in text
        assert "chatbrowser>=0.1.2,<0.2.0" in text
        assert "attach_existing_cdp = false" in text
        assert "手机号" in text or "phone" in text
        assert "验证码" in text or "verification code" in text
        assert "post publish" in text
        assert "final" in text or "最终" in text
        assert "chatup.chrome_for_testing" not in text


def test_attach_existing_cdp_is_documented_as_runner_config_only():
    for relative in ("docs/configuration.md", "docs/configuration.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "attach_existing_cdp = false" in text
        assert "手机号" in text or "phone" in text
        assert "验证码" in text or "verification code" in text
        runner_start = text.index("[runners.zhihu-personal]")
        account_start = text.index('[accounts."zhihu@personal"]')
        assert runner_start < text.index("attach_existing_cdp = false") < account_start
        account_block = text[account_start : text.index("```", account_start)]
        assert "attach_existing_cdp" not in account_block
        assert "LEFT_RUNNING_EXISTING_CDP" in text


def test_extension_bridge_wake_contract_is_documented():
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "mcpToken" in changelog
    assert "MCP_SET_SERVER_URL" in changelog
    assert "payload.url" in changelog
    assert "MCP_WATCH_START" in changelog


def test_mkdocs_quickstart_is_the_daily_login_to_draft_entrypoint():
    mkdocs = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "快速开始: quickstart.md" in mkdocs
    assert "快速开始: Quickstart" in mkdocs

    zh_home = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    en_home = (ROOT / "docs/index.en.md").read_text(encoding="utf-8")
    zh_readme = (ROOT / "README.md").read_text(encoding="utf-8")
    en_readme = (ROOT / "README.en.md").read_text(encoding="utf-8")
    assert "[Quickstart：从登录到发送草稿](quickstart.md)" in zh_home
    assert "[Quickstart: From Login to Draft Creation](quickstart.md)" in en_home
    assert "[Quickstart：从登录到发送草稿](docs/quickstart.md)" in zh_readme
    assert "[Quickstart: From Login to Draft Creation](docs/quickstart.en.md)" in en_readme

    for relative in ("docs/quickstart.md", "docs/quickstart.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "chatpost zhihu draft dry-run" not in text
        assert "chatpost zhihu draft create" not in text
        assert "--dry-run" in text
        assert "--receipt" in text
        assert "READY" in text
        assert "RESULT_UNKNOWN" in text
        assert "page-owned `login_url`" in text
        assert "screenshot" in text or "截图" in text
        assert "not final-publish" in text or "不点击最终发布" in text
        assert "--phone" in text
        assert "--sms-code" in text
        assert "Cookie" in text or "cookies" in text
        assert "LocalStorage" in text or "local storage" in text
        assert "review URL" in text


def test_quick_start_keeps_create_update_and_publish_boundaries_explicit():
    for relative in ("docs/zhihu-first-run.md", "docs/zhihu-first-run.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "quickstart.md" in text
        assert "RESULT_UNKNOWN" in text
        assert "--dry-run" in text
        assert "--receipt" in text
        assert "1.61.1" in text
        assert "1228" in text
        assert "149.0.7827.55" in text
        assert "0073787cfbff0f7af4d1b427da3adbb16d92eeb8" in text
        assert "same-ID" in text
        assert "Cookie" in text or "cookie" in text
        assert "`preview`" in text
        assert "Browser.close" in text
        assert "chatpost-run-*" in text
        assert "WebSocket UUID" in text
        assert "Target.createTarget" in text
        assert "Target.attachToTarget" in text
        assert "Target.closeTarget" in text
        assert "extension_cleanup_status" in text
        assert "stale popup" in text
        assert "listener PID" in text
        assert "MANUAL_RECOVERY_REQUIRED" in text
        assert "adapter_cleanup_status" in text
        assert "review URL" in text
        if relative.endswith(".en.md"):
            assert "Receipts record browser `cleanup_status`" in text
            assert "fail closed to `[REDACTED]`" in text
            assert "receipt could not be written" in text
            assert "numeric IPv4 loopback `127.0.0.1`" in text
            assert "multi-line structured private assignments" in text
            assert "source_sha256 is captured before the browser or adapter starts" in text
            assert "post-wake output-read failure" in text
        else:
            assert "receipt 分别记录 browser `cleanup_status`" in text
            assert "fail-closed 为 `[REDACTED]`" in text
            assert "receipt 无法落盘" in text
            assert "数值 IPv4 loopback `127.0.0.1`" in text
            assert "跨行结构化私密赋值" in text
            assert "source_sha256 在 browser 或 adapter 启动前捕获" in text
            assert "唤醒后的输出读取失败" in text
