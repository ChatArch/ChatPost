import json
from pathlib import Path

import click
from click.testing import CliRunner

import chatpost.cli as cli
from chatpost.cli import main


def _registry(tmp_path: Path) -> Path:
    runner = tmp_path / "runner.toml"
    runner.write_text("[zhihu]\n", encoding="utf-8")
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        'profile = "zhihu-test"\n'
        'label = "Zhihu test account"\n',
        encoding="utf-8",
    )
    return registry


def _json(result):
    assert result.exit_code == 0, result.output
    return json.loads(result.output)


def test_task_cli_exposes_profile_based_zhihu_surface_and_hides_advanced_helpers():
    assert set(main.commands) == {"account", "platforms", "profiles", "qr", "zhihu"}
    assert main.commands["account"].hidden is True
    assert main.commands["qr"].hidden is True
    assert main.commands["platforms"].hidden is False
    assert main.commands["profiles"].hidden is False

    zhihu = main.commands["zhihu"]
    assert {"profiles", "login", "logout", "status", "draft"}.issubset(zhihu.commands)
    assert zhihu.commands["profiles"].hidden is False
    assert zhihu.commands["login"].hidden is False
    assert zhihu.commands["logout"].hidden is False
    assert zhihu.commands["status"].hidden is False
    assert zhihu.commands["draft"].hidden is False
    assert not isinstance(zhihu.commands["draft"], click.Group)

    # Keep low-level/legacy account helpers callable for scripts, but not as the daily-use CLI.
    assert "account" in zhihu.commands
    assert zhihu.commands["account"].hidden is True
    assert set(zhihu.commands["account"].commands) == {"preflight", "status", "login"}
    assert set(zhihu.commands["account"].commands["login"].commands) == {
        "qr",
        "qr-artifact",
        "code",
    }


def test_top_level_tree_prints_profile_based_registered_cli_tree():
    result = CliRunner().invoke(main, ["--tree"])

    assert result.exit_code == 0, result.output
    assert "chatpost  # platform content publishing and draft orchestration" in result.output
    assert "├── platforms [--output text|json] [-I/--no-interactive]  # List supported publishing platforms." in result.output
    assert "├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Chrome/profile targets." in result.output
    assert "└── zhihu  # Zhihu platform capabilities" in result.output
    assert "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu Chrome/profile targets." in result.output
    assert "    ├── login PROFILE [--registry PATH] [--qr PATH] [--receipt PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Check auth first; emit QR only if login is needed." in result.output
    assert "    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check auth first; clear Zhihu state only if logged in." in result.output
    assert "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check." in result.output
    assert "    └── draft PROFILE SOURCE [--registry PATH] [--receipt PATH] [--dry-run] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu review draft." in result.output
    assert "draft dry-run" not in result.output
    assert "draft create" not in result.output
    assert "account login qr" not in result.output
    assert "qr-artifact" not in result.output
    assert "MEDIA:ssh" not in result.output
    assert "[media attachment]" not in result.output


def test_top_level_help_shows_discovery_and_platform_groups_only():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0, result.output
    assert "platforms" in result.output
    assert "profiles" in result.output
    assert "zhihu" in result.output
    assert "\n  account" not in result.output
    assert "\n  qr" not in result.output
    assert "\n  login" not in result.output
    assert "\n  post" not in result.output
    assert "--tree" in result.output


def test_account_list_reads_non_sensitive_registry(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["account", "list", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["accounts"] == [
        {
            "alias": "zhihu-test",
            "platform": "zhihu",
            "profile": "zhihu-test",
            "label": "Zhihu test account",
            "runner_config": str(tmp_path / "runner.toml"),
        }
    ]
    assert "token" not in result.output.lower()
    assert "cookie" not in result.output.lower()


def test_account_show_resolves_platform_target(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        [
            "account",
            "show",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["account"]["alias"] == "zhihu-test"
    assert payload["account"]["platform"] == "zhihu"


def test_platforms_lists_supported_platforms():
    result = CliRunner().invoke(main, ["platforms", "--output", "json", "-I"])
    payload = _json(result)

    assert payload == {
        "status": "READY",
        "platforms": [
            {
                "name": "zhihu",
                "profiles_command": "chatpost zhihu profiles",
                "login_command": "chatpost zhihu login PROFILE",
                "status_command": "chatpost zhihu status PROFILE",
                "logout_command": "chatpost zhihu logout PROFILE",
            }
        ],
    }


def test_profiles_lists_chrome_profile_configs_and_filters_platform(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["profiles", "--platform", "zhihu", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["profiles"] == [
        {
            "alias": "zhihu-test",
            "platform": "zhihu",
            "profile": "zhihu-test",
            "label": "Zhihu test account",
            "runner_config": str(tmp_path / "runner.toml"),
        }
    ]
    assert "cookie" not in result.output.lower()
    assert "localstorage" not in result.output.lower()


def test_zhihu_profiles_lists_zhihu_profile_configs(tmp_path):
    registry = _registry(tmp_path)

    result = CliRunner().invoke(
        main,
        ["zhihu", "profiles", "--registry", str(registry), "--output", "json", "-I"],
    )
    payload = _json(result)

    assert payload["status"] == "READY"
    assert payload["platform"] == "zhihu"
    assert payload["profiles"][0]["alias"] == "zhihu-test"


def test_zhihu_status_dispatches_read_only_auth(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "execute_task",
        lambda config, source, *, mode: calls.append((config, source, mode))
        or {"status": "READY"},
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

    assert calls == [(("config", tmp_path / "runner.toml"), None, "auth")]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"


def test_zhihu_login_dispatches_single_qr_handoff_command(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    qr = tmp_path / "login.png"
    receipt_path = tmp_path / "login.json"
    scan_link = "https://www.zhihu.com/account/scan/login/waiting?/api/login/qrcode"
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_wait_for_login(
        config,
        *,
        timeout,
        method="qr",
        checkpoint_artifact=None,
        checkpoint_callback=None,
    ):
        calls.append((config, timeout, method, checkpoint_artifact, checkpoint_callback))
        assert checkpoint_callback is not None
        checkpoint_callback(
            {
                "status": "CHECKPOINT_IMAGE_READY",
                "login_method": method,
                "artifact_path": str(checkpoint_artifact),
                "artifact_mime": "image/png",
                "login_url": scan_link,
            }
        )
        return {"status": "READY", "login_method": method, "login_url": scan_link}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "login",
            "zhihu-test",
            "--registry",
            str(registry),
            "--qr",
            str(qr),
            "--receipt",
            str(receipt_path),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), 60, "qr", qr, calls[0][4])]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_url"] == scan_link
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "CHECKPOINT_IMAGE_READY"
    assert receipt["target"] == "zhihu@zhihu-test"
    assert receipt["login_url"] == scan_link
    assert receipt["artifact_path"] == str(qr)
    assert receipt_path.stat().st_mode & 0o077 == 0
    assert "media:ssh" not in result.output.lower()


def test_zhihu_logout_dispatches_profile_logout_without_reading_session(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "logout_from_zhihu",
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

    assert calls == [("config", tmp_path / "runner.toml")]
    assert payload["status"] == "LOGGED_OUT"
    assert payload["target"] == "zhihu@zhihu-test"
    lower = result.output.lower()
    assert "cookie" not in lower
    assert "localstorage" not in lower


def test_zhihu_account_status_dispatches_read_only_auth(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "execute_task",
        lambda config, source, *, mode: calls.append((config, source, mode))
        or {"status": "READY"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "status",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), None, "auth")]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"


def test_zhihu_account_preflight_dispatches_runner_preflight(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "preflight",
        lambda config: calls.append(config) or {"status": "READY", "browser_version": "149"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "preflight",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [("config", tmp_path / "runner.toml")]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"


def test_zhihu_account_login_qr_dispatches_manual_checkpoint(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    def fake_wait_for_login(
        config,
        *,
        timeout,
        method="qr",
        checkpoint_artifact=None,
        checkpoint_callback=None,
    ):
        calls.append((config, timeout, method, checkpoint_artifact, checkpoint_callback))
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "login",
            "qr",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), 60, "qr", None, None)]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_method"] == "qr"


def test_zhihu_account_login_qr_can_emit_checkpoint_receipt_while_waiting(
    monkeypatch, tmp_path
):
    registry = _registry(tmp_path)
    artifact = tmp_path / "wait-login.png"
    receipt_path = tmp_path / "wait-login-ready.json"
    scan_link = "https://www.zhihu.com/account/scan/login/waiting?/api/login/qrcode"
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_wait_for_login(
        config,
        *,
        timeout,
        method="qr",
        checkpoint_artifact=None,
        checkpoint_callback=None,
    ):
        calls.append((config, timeout, method, checkpoint_artifact, checkpoint_callback))
        assert checkpoint_callback is not None
        checkpoint_callback(
            {
                "status": "CHECKPOINT_IMAGE_READY",
                "login_method": method,
                "artifact_path": str(checkpoint_artifact),
                "artifact_mime": "image/png",
                "login_url": scan_link,
            }
        )
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "login",
            "qr",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [
        (("config", tmp_path / "runner.toml"), 60, "qr", artifact, calls[0][4])
    ]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt["status"] == "CHECKPOINT_IMAGE_READY"
    assert receipt["target"] == "zhihu@zhihu-test"
    assert receipt["login_url"] == scan_link
    assert receipt["artifact_path"] == str(artifact)
    assert receipt["receipt_path"] == str(receipt_path)
    assert receipt_path.stat().st_mode & 0o077 == 0


def test_zhihu_account_login_qr_artifact_generates_qr_receipt_and_returns_link(
    monkeypatch, tmp_path
):
    registry = _registry(tmp_path)
    artifact = tmp_path / "live-login.png"
    receipt_path = tmp_path / "live-login.json"
    scan_link = "https://www.zhihu.com/account/scan/login/short-lived?/api/login/qrcode"
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_create_login_qr_artifact(config, destination, *, timeout):
        calls.append((config, destination, timeout))
        destination.write_bytes(b"PNG")
        return {
            "status": "CHECKPOINT_IMAGE_READY",
            "login_method": "qr",
            "artifact_path": str(destination),
            "artifact_mime": "image/png",
            "data_length": len(scan_link),
            "login_url": scan_link,
            "qr_expires_at": 1785921540,
        }

    monkeypatch.setattr(cli, "create_login_qr_artifact", fake_create_login_qr_artifact)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "login",
            "qr-artifact",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--timeout",
            "45",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), artifact, 45)]
    assert artifact.read_bytes() == b"PNG"
    assert payload["status"] == "CHECKPOINT_IMAGE_READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_url"] == scan_link
    assert payload["artifact_path"] == str(artifact)
    assert payload["receipt_path"] == str(receipt_path)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt == payload
    assert receipt_path.stat().st_mode & 0o077 == 0
    lower = receipt_path.read_text(encoding="utf-8").lower() + result.output.lower()
    assert "cookie" not in lower
    assert "localstorage" not in lower
    assert "media:ssh" not in lower


def test_zhihu_account_login_code_dispatches_sms_code_checkpoint_without_phone_or_code(
    monkeypatch, tmp_path
):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_wait_for_login(config, *, timeout, method="qr"):
        calls.append((config, timeout, method))
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "account",
            "login",
            "code",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--timeout",
            "120",
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), 120, "code")]
    assert payload["status"] == "READY"
    assert payload["login_method"] == "code"
    assert payload["target"] == "zhihu@zhihu-test"
    assert "phone" not in result.output.lower()
    assert "verification" not in result.output.lower()
    assert "验证码" not in result.output


def test_zhihu_account_login_code_help_does_not_accept_phone_or_verification_code_values():
    result = CliRunner().invoke(main, ["zhihu", "account", "login", "code", "--help"])

    assert result.exit_code == 0
    assert "--phone" not in result.output
    assert "--code" not in result.output
    assert "verification-code" not in result.output.lower()


def test_qr_encode_writes_artifact_without_echoing_payload_by_default(monkeypatch, tmp_path):
    artifact = tmp_path / "login-url.png"
    calls = []

    def fake_generate_qr_code_image(data, destination):
        calls.append((data, destination))
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png", "data_length": len(data)}

    monkeypatch.setattr(cli, "generate_qr_code_image", fake_generate_qr_code_image)

    result = CliRunner().invoke(
        main,
        [
            "qr",
            "encode",
            "https://www.zhihu.com/signin?login_method=qr",
            "--artifact",
            str(artifact),
            "--output",
            "json",
            "-I",
        ],
    )

    payload = _json(result)
    assert calls == [("https://www.zhihu.com/signin?login_method=qr", artifact)]
    assert payload == {
        "artifact_mime": "image/png",
        "artifact_path": str(artifact),
        "data_length": len("https://www.zhihu.com/signin?login_method=qr"),
        "status": "QR_CODE_READY",
    }
    assert "https://www.zhihu.com" not in result.output


def test_zhihu_draft_dry_run_dispatches_without_browser_write(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# ChatPost draft smoke\n\nGenerated by tests.", encoding="utf-8")
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "execute_task",
        lambda config, source_path, *, mode: calls.append((config, source_path, mode))
        or {"status": "DRY_RUN_OK", "source_sha256": "abc", "preview": "ok"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu@zhihu-test",
            str(source),
            "--dry-run",
            "--registry",
            str(registry),
            "--output",
            "json",
            "-I",
        ],
    )
    payload = _json(result)

    assert calls == [(("config", tmp_path / "runner.toml"), source, "dry-run")]
    assert payload["status"] == "DRY_RUN_OK"
    assert payload["target"] == "zhihu@zhihu-test"


def test_zhihu_draft_create_dispatches_create_and_writes_receipt(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    source.write_text("# ChatPost draft smoke\n\nGenerated by tests.", encoding="utf-8")
    receipt = tmp_path / "receipt.json"
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "execute_task",
        lambda config, source_path, *, mode: calls.append((config, source_path, mode))
        or {
            "status": "DRAFT_CREATED",
            "draft_id": "2067000000000000001",
            "review_url": "https://zhuanlan.zhihu.com/p/2067000000000000001/edit",
            "source_sha256": "abc",
        },
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "draft",
            "zhihu@zhihu-test",
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

    assert calls == [(("config", tmp_path / "runner.toml"), source, "create")]
    assert payload["status"] == "DRAFT_CREATED"
    assert payload["target"] == "zhihu@zhihu-test"
    assert receipt.is_file()
    assert "DRAFT_CREATED" in receipt.read_text(encoding="utf-8")
