import json
import stat
from pathlib import Path

from click.testing import CliRunner

import chatpost.cli as command
from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    runner = tmp_path / "runner.toml"
    runner.write_text("[zhihu]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "zhihu-test"\n',
        encoding="utf-8",
    )
    return registry


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _json_lines(result):
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.output.splitlines() if line.strip()]


def test_zhihu_cli_registers_login_only_surface_without_unreleased_compatibility():
    zhihu = main.commands["zhihu"]

    assert set(zhihu.commands) == {"profiles", "login", "status", "logout", "draft"}
    assert all(command.hidden is False for command in zhihu.commands.values())
    assert "account" not in zhihu.commands
    assert "qr" not in main.commands
    assert "account" not in main.commands


def test_removed_unreleased_surfaces_fail_as_commands():
    runner = CliRunner()

    for args in (
        ["qr", "encode", "https://example.com", "--artifact", "x.png"],
        ["account", "list"],
        ["zhihu", "account", "status", "zhihu-test"],
    ):
        result = runner.invoke(main, args)
        assert result.exit_code != 0, (args, result.output)


def test_draft_dry_run_dispatches_wechat_sync_runner_without_browser_login(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# Title\n\nmarker", encoding="utf-8")
    sentinel = object()
    calls = []

    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "execute_task",
        lambda config, source_path, *, mode: calls.append((config, source_path, mode))
        or {
            "status": "DRY_RUN_OK",
            "source_sha256": "sha256-preview",
            "preview": "adapter preview",
        },
    )
    monkeypatch.setattr(
        command,
        "browser_status",
        lambda _config: (_ for _ in ()).throw(AssertionError("draft must not call browser_status")),
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu-test",
            str(source),
            "--registry",
            str(registry),
            "--dry-run",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(sentinel, source, "dry-run")]
    assert payload == {
        "target": "zhihu@zhihu-test",
        "profile": "zhihu-test",
        "platform": "zhihu",
        "status": "DRY_RUN_OK",
        "source_sha256": "sha256-preview",
        "preview": "adapter preview",
    }


def test_draft_create_requires_receipt_before_adapter_call(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# Title\n\nmarker", encoding="utf-8")
    calls = []
    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())
    monkeypatch.setattr(
        command,
        "execute_task",
        lambda *_args, **_kwargs: calls.append((_args, _kwargs)) or {"status": "DRAFT_CREATED"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu-test",
            str(source),
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )

    assert result.exit_code != 0
    assert "--receipt is required" in result.output
    assert calls == []


def test_draft_create_writes_mode_0600_receipt(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    receipt = tmp_path / "run" / "receipt.json"
    source.write_text("# Title\n\nmarker", encoding="utf-8")
    sentinel = object()
    calls = []

    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "execute_task",
        lambda config, source_path, *, mode: calls.append((config, source_path, mode))
        or {
            "status": "DRAFT_CREATED",
            "draft_id": "12345",
            "review_url": "https://zhuanlan.zhihu.com/p/12345/edit",
            "source_sha256": "sha256-created",
        },
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu-test",
            str(source),
            "--registry",
            str(registry),
            "--receipt",
            str(receipt),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(sentinel, source, "create")]
    assert payload["status"] == "DRAFT_CREATED"
    assert json.loads(receipt.read_text(encoding="utf-8"))["status"] == "DRAFT_CREATED"
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600


def test_draft_result_unknown_writes_receipt_with_recovery_reason(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    receipt = tmp_path / "run" / "unknown.json"
    source.write_text("# Title\n\nmarker", encoding="utf-8")

    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())

    def ambiguous(*_args, **_kwargs):
        raise command.ResultUnknownError(
            "Wechatsync exited successfully without a review URL; do not retry automatically",
            receipt={
                "status": command.RESULT_UNKNOWN,
                "source_sha256": "sha256-unknown",
                "result_unknown_reason": "missing_review_url",
                "cleanup_status": "CLOSED",
                "adapter_cleanup_status": "CLOSED",
            },
        )

    monkeypatch.setattr(command, "execute_task", ambiguous)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu-test",
            str(source),
            "--registry",
            str(registry),
            "--receipt",
            str(receipt),
            "--output",
            "json",
            "-I",
        ],
    )

    assert result.exit_code != 0
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    assert payload["status"] == command.RESULT_UNKNOWN
    assert payload["result_unknown_reason"] == "missing_review_url"
    assert payload["target"] == "zhihu@zhihu-test"
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert "do not retry automatically" in result.output


def test_status_accepts_logical_profile_name_without_platform_alias(monkeypatch, tmp_path):
    runner = tmp_path / "runner.toml"
    runner.write_text("[zhihu]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "test"\n',
        encoding="utf-8",
    )
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "browser_status",
        lambda config: calls.append(config)
        or {
            "status": "LOGGED_OUT",
            "check_method": "browser_page",
        },
    )

    result = CliRunner().invoke(
        main,
        ["zhihu", "status", "test", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert calls == [sentinel]
    assert payload == {
        "target": "zhihu@test",
        "profile": "test",
        "platform": "zhihu",
        "status": "LOGGED_OUT",
        "check_method": "browser_page",
    }


def test_status_dispatches_browser_level_status_without_adapter_auth(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "browser_status",
        lambda config: calls.append(config)
        or {
            "status": "LOGGED_IN",
            "account_name": "RexWang",
            "account_url": "https://www.zhihu.com/people/rexwang",
            "check_method": "browser_page",
        },
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "status",
            "zhihu-test",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [sentinel]
    assert payload == {
        "target": "zhihu@zhihu-test",
        "profile": "zhihu-test",
        "platform": "zhihu",
        "status": "LOGGED_IN",
        "account_name": "RexWang",
        "account_url": "https://www.zhihu.com/people/rexwang",
        "check_method": "browser_page",
    }
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "token" not in lower
    assert "cookie" not in lower


def test_login_dispatches_browser_level_handoff_and_streams_login_url(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_browser_config", lambda _path: sentinel)

    def fake_browser_login(config, *, timeout, event_callback=None):
        calls.append((config, timeout, event_callback))
        assert event_callback is not None
        event_callback(
            {
                "event": "login_url",
                "status": "LOGIN_REQUIRED",
                "login_url": "https://www.zhihu.com/account/scan/login/page-owned",
                "check_method": "browser_page",
            }
        )
        return {
            "event": "logged_in",
            "status": "LOGGED_IN",
            "account_name": "RexWang",
            "account_url": "https://www.zhihu.com/people/rexwang",
            "check_method": "browser_page",
        }

    monkeypatch.setattr(command, "browser_login", fake_browser_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "login",
            "zhihu-test",
            "--registry",
            str(registry),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )
    events = _json_lines(result)

    assert calls == [(sentinel, 60, calls[0][2])]
    assert events == [
        {
            "event": "login_url",
            "target": "zhihu@zhihu-test",
            "profile": "zhihu-test",
            "platform": "zhihu",
            "status": "LOGIN_REQUIRED",
            "login_url": "https://www.zhihu.com/account/scan/login/page-owned",
            "check_method": "browser_page",
        },
        {
            "event": "logged_in",
            "target": "zhihu@zhihu-test",
            "profile": "zhihu-test",
            "platform": "zhihu",
            "status": "LOGGED_IN",
            "account_name": "RexWang",
            "account_url": "https://www.zhihu.com/people/rexwang",
            "check_method": "browser_page",
        },
    ]
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "artifact" not in lower
    assert "receipt" not in lower
    assert "media:ssh" not in lower


def test_logout_dispatches_browser_level_logout_without_adapter_auth(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "browser_logout",
        lambda config: calls.append(config)
        or {"status": "LOGGED_OUT", "logout_method": "clear_origin_storage"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "logout",
            "zhihu-test",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [sentinel]
    assert payload == {
        "target": "zhihu@zhihu-test",
        "profile": "zhihu-test",
        "platform": "zhihu",
        "status": "LOGGED_OUT",
        "logout_method": "clear_origin_storage",
    }
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "cookie" not in lower
    assert "token" not in lower
