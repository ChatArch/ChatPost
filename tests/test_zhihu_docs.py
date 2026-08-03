from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cli_tree_matches_registered_task_commands():
    for relative in ("docs/cli-tree.md", "docs/cli-tree.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        for command in (
            "chatpost zhihu preflight",
            "chatpost zhihu login",
            "chatpost zhihu auth",
            "chatpost zhihu draft dry-run",
            "chatpost zhihu draft create",
        ):
            assert command in text
        assert "chatup playwright install 1.61.1" in text
        assert "chatup.playwright" in text
        assert "chatup.chrome_for_testing" not in text


def test_quick_start_keeps_create_update_and_publish_boundaries_explicit():
    for relative in ("docs/zhihu-first-run.md", "docs/zhihu-first-run.en.md"):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "RESULT_UNKNOWN" in text
        assert "draft create" in text
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
        assert "MANUAL_RECOVERY_REQUIRED" in text
        if relative.endswith(".en.md"):
            assert "The `RESULT_UNKNOWN` receipt also records `cleanup_status`" in text
            assert "fail closed to `[REDACTED]`" in text
        else:
            assert "`RESULT_UNKNOWN` receipt 同样记录 `cleanup_status`" in text
            assert "fail-closed 为 `[REDACTED]`" in text
