import json
import stat
from pathlib import Path

from click.testing import CliRunner

import chatpost.cli as command
from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    runner = tmp_path / "xiaohongshu-runner.toml"
    runner.write_text("[xiaohongshu]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."xhs-test"]\n'
        'platform = "xiaohongshu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "xhs-test"\n',
        encoding="utf-8",
    )
    return registry


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _json_lines(result):
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.output.splitlines() if line.strip()]


def test_xiaohongshu_cli_registers_platform_surface_without_global_shortcuts():
    xiaohongshu = main.commands["xiaohongshu"]

    assert set(xiaohongshu.commands) == {"profiles", "login", "status", "logout", "draft"}
    assert all(command.hidden is False for command in xiaohongshu.commands.values())
    assert "account" not in xiaohongshu.commands
    assert "qr" not in main.commands
    assert "xiaohongshu-login" not in main.commands


def test_xiaohongshu_status_dispatches_browser_level_status_without_adapter(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xiaohongshu_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "xiaohongshu_browser_status",
        lambda config: calls.append(config)
        or {
            "status": "LOGGED_IN",
            "account_name": "XHS User",
            "account_url": "https://www.xiaohongshu.com/user/profile/abc123",
            "check_method": "browser_page",
        },
    )

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "status",
            "xhs-test",
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
        "target": "xiaohongshu@xhs-test",
        "profile": "xhs-test",
        "platform": "xiaohongshu",
        "status": "LOGGED_IN",
        "account_name": "XHS User",
        "account_url": "https://www.xiaohongshu.com/user/profile/abc123",
        "check_method": "browser_page",
    }
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "token" not in lower
    assert "cookie" not in lower


def test_xiaohongshu_login_dispatches_browser_level_handoff(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xiaohongshu_browser_config", lambda _path: sentinel)

    def fake_browser_login(config, *, timeout, event_callback=None):
        calls.append((config, timeout, event_callback))
        assert event_callback is not None
        event_callback(
            {
                "event": "login_url",
                "status": "LOGIN_REQUIRED",
                "login_url": "https://www.xiaohongshu.com/login",
                "handoff_kind": "browser_opened",
                "check_method": "browser_page",
            }
        )
        return {
            "event": "logged_in",
            "status": "LOGGED_IN",
            "account_name": "XHS User",
            "account_url": "https://www.xiaohongshu.com/user/profile/abc123",
            "check_method": "browser_page",
        }

    monkeypatch.setattr(command, "xiaohongshu_browser_login", fake_browser_login)

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "login",
            "xhs-test",
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
            "target": "xiaohongshu@xhs-test",
            "profile": "xhs-test",
            "platform": "xiaohongshu",
            "status": "LOGIN_REQUIRED",
            "login_url": "https://www.xiaohongshu.com/login",
            "handoff_kind": "browser_opened",
            "check_method": "browser_page",
        },
        {
            "event": "logged_in",
            "target": "xiaohongshu@xhs-test",
            "profile": "xhs-test",
            "platform": "xiaohongshu",
            "status": "LOGGED_IN",
            "account_name": "XHS User",
            "account_url": "https://www.xiaohongshu.com/user/profile/abc123",
            "check_method": "browser_page",
        },
    ]
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "media:ssh" not in lower
    assert "receipt" not in lower


def test_xiaohongshu_logout_dispatches_browser_level_logout(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xiaohongshu_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "xiaohongshu_browser_logout",
        lambda config: calls.append(config)
        or {"status": "LOGGED_OUT", "logout_method": "clear_origin_storage"},
    )

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "logout",
            "xhs-test",
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
        "target": "xiaohongshu@xhs-test",
        "profile": "xhs-test",
        "platform": "xiaohongshu",
        "status": "LOGGED_OUT",
        "logout_method": "clear_origin_storage",
    }


def test_xiaohongshu_draft_dry_run_validates_source_without_browser_login(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# Title\n\n小红书草稿", encoding="utf-8")
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xiaohongshu_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "xiaohongshu_execute_task",
        lambda config, source_path, *, mode: calls.append((config, source_path, mode))
        or {
            "status": "DRY_RUN_OK",
            "source_sha256": "sha256-preview",
            "preview": "local source parsed; create adapter not connected",
        },
    )
    monkeypatch.setattr(
        command,
        "xiaohongshu_browser_status",
        lambda _config: (_ for _ in ()).throw(AssertionError("draft dry-run must not call browser_status")),
    )

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "draft",
            "xhs-test",
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
        "target": "xiaohongshu@xhs-test",
        "profile": "xhs-test",
        "platform": "xiaohongshu",
        "status": "DRY_RUN_OK",
        "source_sha256": "sha256-preview",
        "preview": "local source parsed; create adapter not connected",
    }


def test_xiaohongshu_draft_create_requires_receipt_before_adapter_call(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "note.md"
    source.write_text("# Title\n\n小红书草稿", encoding="utf-8")
    calls = []
    monkeypatch.setattr(command, "load_xiaohongshu_runner_config", lambda _path: object())
    monkeypatch.setattr(
        command,
        "xiaohongshu_execute_task",
        lambda *_args, **_kwargs: calls.append((_args, _kwargs)) or {"status": "DRAFT_CREATED"},
    )

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "draft",
            "xhs-test",
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


def test_xiaohongshu_draft_create_writes_unsupported_receipt_and_fails(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "note.md"
    receipt = tmp_path / "run" / "xhs-receipt.json"
    source.write_text("# Title\n\n小红书草稿", encoding="utf-8")
    monkeypatch.setattr(command, "load_xiaohongshu_runner_config", lambda _path: object())

    def unsupported(*_args, **_kwargs):
        raise command.XiaohongshuDraftNotSupportedError(
            "Xiaohongshu draft create adapter is not connected; no remote write was attempted",
            receipt={
                "status": "CREATE_NOT_SUPPORTED",
                "source_sha256": "sha256-unsupported",
                "reason": "adapter_not_connected",
            },
        )

    monkeypatch.setattr(command, "xiaohongshu_execute_task", unsupported)

    result = CliRunner().invoke(
        main,
        [
            "xiaohongshu",
            "draft",
            "xhs-test",
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
    assert payload == {
        "target": "xiaohongshu@xhs-test",
        "profile": "xhs-test",
        "platform": "xiaohongshu",
        "status": "CREATE_NOT_SUPPORTED",
        "source_sha256": "sha256-unsupported",
        "reason": "adapter_not_connected",
    }
    assert stat.S_IMODE(receipt.stat().st_mode) == 0o600
    assert "no remote write was attempted" in result.output
