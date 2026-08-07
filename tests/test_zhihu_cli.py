import json
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

    assert set(zhihu.commands) == {"profiles", "login", "status", "logout"}
    assert all(command.hidden is False for command in zhihu.commands.values())
    assert "draft" not in zhihu.commands
    assert "account" not in zhihu.commands
    assert "qr" not in main.commands
    assert "account" not in main.commands


def test_removed_unreleased_surfaces_fail_as_commands():
    runner = CliRunner()

    for args in (
        ["qr", "encode", "https://example.com", "--artifact", "x.png"],
        ["account", "list"],
        ["zhihu", "account", "status", "zhihu-test"],
        ["zhihu", "draft", "zhihu-test", "article.md"],
    ):
        result = runner.invoke(main, args)
        assert result.exit_code != 0, (args, result.output)


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
