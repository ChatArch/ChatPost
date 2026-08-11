import json
from pathlib import Path

from click.testing import CliRunner

import chatpost.cli as command
from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    runner = tmp_path / "csdn-runner.toml"
    runner.write_text(
        "[csdn]\n"
        "playwright_version = \"1.0.0\"\n"
        f"playwright_home = {json.dumps(str(tmp_path / 'pw'))}\n"
        f"profile_dir = {json.dumps(str(tmp_path / 'profile'))}\n"
        "cdp_host = \"127.0.0.1\"\n"
        "cdp_port = 9444\n"
        "headless = true\n"
        "browser_args = []\n",
        encoding="utf-8",
    )
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."csdn-test"]\n'
        'platform = "csdn"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "test"\n'
        'label = "CSDN test account"\n',
        encoding="utf-8",
    )
    return registry


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def _json_lines(result):
    assert result.exit_code == 0, result.output
    return [json.loads(line) for line in result.output.splitlines() if line.strip()]


def test_csdn_cli_registers_login_only_surface_without_draft():
    csdn = main.commands["csdn"]

    assert set(csdn.commands) == {"profiles", "login", "status", "logout"}
    assert all(command.hidden is False for command in csdn.commands.values())
    assert "draft" not in csdn.commands
    assert "account" not in csdn.commands


def test_csdn_status_accepts_logical_profile_name_without_platform_alias(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_csdn_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "csdn_browser_status",
        lambda config: calls.append(config)
        or {
            "status": "LOGGED_IN",
            "account_name": "致宏Rex",
            "check_method": "browser_page",
        },
    )

    result = CliRunner().invoke(
        main,
        ["csdn", "status", "test", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert calls == [sentinel]
    assert payload == {
        "target": "csdn@test",
        "profile": "test",
        "platform": "csdn",
        "status": "LOGGED_IN",
        "account_name": "致宏Rex",
        "check_method": "browser_page",
    }
    lower = result.output.lower()
    assert "token" not in lower
    assert "cookie" not in lower
    assert "session" not in lower
    assert "avatar" not in lower
    assert "user_id" not in lower
    assert "account_url" not in lower


def test_csdn_login_dispatches_browser_level_qr_image_handoff(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    qr_path = tmp_path / "csdn-login-qr.png"
    png_data_url = (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    calls = []
    monkeypatch.setattr(command, "load_csdn_browser_config", lambda _path: sentinel)

    def fake_browser_login(config, *, timeout, event_callback=None):
        calls.append((config, timeout, event_callback))
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
            "event": "logged_in",
            "status": "LOGGED_IN",
            "account_name": "致宏Rex",
            "check_method": "browser_page",
        }

    monkeypatch.setattr(command, "csdn_browser_login", fake_browser_login)

    result = CliRunner().invoke(
        main,
        [
            "csdn",
            "login",
            "csdn-test",
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

    assert calls == [(sentinel, 60, calls[0][2])]
    assert qr_path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert qr_path.stat().st_mode & 0o777 == 0o600
    assert events == [
        {
            "event": "login_handoff",
            "target": "csdn@csdn-test",
            "profile": "csdn-test",
            "platform": "csdn",
            "status": "LOGIN_REQUIRED",
            "handoff_kind": "qrcode_image",
            "qrcode_path": str(qr_path.resolve()),
            "check_method": "browser_page",
        },
        {
            "event": "logged_in",
            "target": "csdn@csdn-test",
            "profile": "csdn-test",
            "platform": "csdn",
            "status": "LOGGED_IN",
            "account_name": "致宏Rex",
            "check_method": "browser_page",
        },
    ]
    lower = result.output.lower()
    assert "login_url" not in lower
    assert "data:image" not in lower
    assert "base64," not in lower
    assert "qrcode_data_url" not in lower
    assert "media:ssh" not in lower


def test_csdn_logout_dispatches_browser_level_logout(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_csdn_browser_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "csdn_browser_logout",
        lambda config: calls.append(config)
        or {"status": "LOGGED_OUT", "logout_method": "clear_origin_storage"},
    )

    result = CliRunner().invoke(
        main,
        [
            "csdn",
            "logout",
            "csdn-test",
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
        "target": "csdn@csdn-test",
        "profile": "csdn-test",
        "platform": "csdn",
        "status": "LOGGED_OUT",
        "logout_method": "clear_origin_storage",
    }
