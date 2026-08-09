import json
from pathlib import Path

from click.testing import CliRunner

import chatpost.cli as command
from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    runner = tmp_path / "xhs-runner.toml"
    runner.write_text("[xhs]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."xhs-test"]\n'
        'platform = "xhs"\n'
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


def test_xhs_cli_registers_short_platform_surface_without_draft_or_long_alias():
    xhs = main.commands["xhs"]

    assert set(xhs.commands) == {"profiles", "login", "status", "logout"}
    assert all(command.hidden is False for command in xhs.commands.values())
    assert "draft" not in xhs.commands
    assert "xiaohongshu" not in main.commands
    assert "account" not in xhs.commands
    assert "qr" not in main.commands
    assert "xhs-login" not in main.commands


def test_xhs_status_dispatches_browser_level_status_without_adapter(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xhs_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "xhs_browser_status",
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
            "xhs",
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
        "target": "xhs@xhs-test",
        "profile": "xhs-test",
        "platform": "xhs",
        "status": "LOGGED_IN",
        "account_name": "XHS User",
        "account_url": "https://www.xiaohongshu.com/user/profile/abc123",
        "check_method": "browser_page",
    }
    lower = result.output.lower()
    assert "wechatsync" not in lower
    assert "token" not in lower
    assert "cookie" not in lower


def test_xhs_login_dispatches_browser_level_handoff(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xhs_browser_config", lambda _path: sentinel)

    def fake_browser_login(config, *, timeout, event_callback=None):
        calls.append((config, timeout, event_callback))
        assert event_callback is not None
        event_callback(
            {
                "event": "login_url",
                "status": "LOGIN_REQUIRED",
                "login_url": "https://www.xiaohongshu.com/explore",
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

    monkeypatch.setattr(command, "xhs_browser_login", fake_browser_login)

    result = CliRunner().invoke(
        main,
        [
            "xhs",
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
            "target": "xhs@xhs-test",
            "profile": "xhs-test",
            "platform": "xhs",
            "status": "LOGIN_REQUIRED",
            "login_url": "https://www.xiaohongshu.com/explore",
            "handoff_kind": "browser_opened",
            "check_method": "browser_page",
        },
        {
            "event": "logged_in",
            "target": "xhs@xhs-test",
            "profile": "xhs-test",
            "platform": "xhs",
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


def test_xhs_login_writes_qrcode_artifact_and_suppresses_data_url(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    qr_path = tmp_path / "login-qr.png"
    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    monkeypatch.setattr(command, "load_xhs_browser_config", lambda _path: sentinel)

    def fake_browser_login(config, *, timeout, event_callback=None):
        assert config is sentinel
        assert timeout == 60
        assert event_callback is not None
        event_callback(
            {
                "event": "login_handoff",
                "status": "LOGIN_REQUIRED",
                "login_url": None,
                "handoff_kind": "qrcode_image",
                "qrcode_data_url": png_data_url,
                "check_method": "browser_page",
            }
        )
        return {
            "event": "login_timeout",
            "status": "LOGIN_TIMEOUT",
            "login_url": None,
            "handoff_kind": "qrcode_image",
            "qrcode_data_url": png_data_url,
            "check_method": "browser_page",
        }

    monkeypatch.setattr(command, "xhs_browser_login", fake_browser_login)

    result = CliRunner().invoke(
        main,
        [
            "xhs",
            "login",
            "xhs-test",
            "--registry",
            str(registry),
            "--timeout",
            "60",
            "--qrcode",
            str(qr_path),
            "--output",
            "json",
            "-I",
        ],
    )
    events = _json_lines(result)

    assert qr_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert qr_path.stat().st_mode & 0o777 == 0o600
    assert events == [
        {
            "event": "login_handoff",
            "target": "xhs@xhs-test",
            "profile": "xhs-test",
            "platform": "xhs",
            "status": "LOGIN_REQUIRED",
            "login_url": None,
            "handoff_kind": "qrcode_image",
            "qrcode_path": str(qr_path.resolve()),
            "check_method": "browser_page",
        },
        {
            "event": "login_timeout",
            "target": "xhs@xhs-test",
            "profile": "xhs-test",
            "platform": "xhs",
            "status": "LOGIN_TIMEOUT",
            "login_url": None,
            "handoff_kind": "qrcode_image",
            "qrcode_path": str(qr_path.resolve()),
            "check_method": "browser_page",
        },
    ]
    assert "qrcode_data_url" not in result.output
    assert "iVBOR" not in result.output


def test_xhs_logout_dispatches_browser_level_logout(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_xhs_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "xhs_browser_logout",
        lambda config: calls.append(config)
        or {"status": "LOGGED_OUT", "logout_method": "clear_origin_storage"},
    )

    result = CliRunner().invoke(
        main,
        [
            "xhs",
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
        "target": "xhs@xhs-test",
        "profile": "xhs-test",
        "platform": "xhs",
        "status": "LOGGED_OUT",
        "logout_method": "clear_origin_storage",
    }
