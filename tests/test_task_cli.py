import json
from pathlib import Path

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


def test_task_cli_exposes_platform_scoped_zhihu_groups_and_tree():
    assert set(main.commands) == {"account", "qr", "zhihu"}
    assert {"list", "show"}.issubset(main.commands["account"].commands)
    assert {"encode"}.issubset(main.commands["qr"].commands)

    zhihu = main.commands["zhihu"]
    assert set(zhihu.commands) == {"account", "draft"}
    assert set(zhihu.commands["account"].commands) == {"preflight", "status", "login"}
    assert set(zhihu.commands["account"].commands["login"].commands) == {
        "qr",
        "qr-artifact",
        "code",
    }
    assert set(zhihu.commands["draft"].commands) == {"dry-run", "create"}


def test_top_level_tree_prints_platform_scoped_registered_cli_tree():
    result = CliRunner().invoke(main, ["--tree"])

    assert result.exit_code == 0, result.output
    assert "chatpost  # platform content publishing and draft orchestration" in result.output
    assert "├── account  # account alias registry; metadata only" in result.output
    assert "├── qr  # platform-neutral QR artifact tools" in result.output
    assert "└── zhihu  # Zhihu platform capabilities" in result.output
    assert "    ├── account  # Zhihu account status, preflight, and login checkpoints" in result.output
    assert "    │   ├── status TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check." in result.output
    assert "    │       ├── qr TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open QR login checkpoint and wait for READY." in result.output
    assert "    │       ├── qr-artifact TARGET [--registry PATH] --artifact PATH --receipt PATH [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Create live QR PNG + receipt, return immediately." in result.output
    assert "    └── draft  # Zhihu review-draft operations" in result.output
    assert "        └── create TARGET SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft." in result.output
    assert "chatpost login" not in result.output
    assert "chatpost post" not in result.output
    assert "MEDIA:ssh" not in result.output
    assert "[media attachment]" not in result.output


def test_top_level_help_hides_old_global_login_and_post_groups():
    result = CliRunner().invoke(main, ["--help"])

    assert result.exit_code == 0, result.output
    assert "account" in result.output
    assert "qr" in result.output
    assert "zhihu" in result.output
    assert "login" not in result.output
    assert "post" not in result.output
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
    monkeypatch.setattr(
        cli,
        "wait_for_login",
        lambda config, *, timeout, method="qr": calls.append((config, timeout, method))
        or {"status": "READY", "login_method": method},
    )

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

    assert calls == [(("config", tmp_path / "runner.toml"), 60, "qr")]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_method"] == "qr"


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
            "dry-run",
            "zhihu@zhihu-test",
            str(source),
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
            "create",
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
