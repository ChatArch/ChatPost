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


def test_task_cli_exposes_common_account_login_and_post_groups():
    assert {"account", "login", "post", "qr", "zhihu"}.issubset(main.commands)
    assert {"list", "show"}.issubset(main.commands["account"].commands)
    assert {"status", "qr", "qr-image", "qr-link", "code"}.issubset(
        main.commands["login"].commands
    )
    assert {"draft"}.issubset(main.commands["post"].commands)
    assert {"encode"}.issubset(main.commands["qr"].commands)


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


def test_login_status_dispatches_read_only_auth(monkeypatch, tmp_path):
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
            "login",
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


def test_login_qr_dispatches_manual_checkpoint(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))
    monkeypatch.setattr(
        cli,
        "wait_for_login",
        lambda config, timeout: calls.append((config, timeout)) or {"status": "READY"},
    )

    result = CliRunner().invoke(
        main,
        [
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

    assert calls == [(('config', tmp_path / "runner.toml"), 60)]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"


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


def test_login_qr_link_writes_clickable_url_receipt_and_qr_artifact(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    artifact = tmp_path / "login-link.png"
    receipt_path = tmp_path / "login-link.json"
    calls = []

    def fake_generate_qr_code_image(data, destination):
        calls.append((data, destination))
        destination.write_bytes(b"PNG")
        return {"artifact_path": str(destination), "artifact_mime": "image/png", "data_length": len(data)}

    monkeypatch.setattr(cli, "generate_qr_code_image", fake_generate_qr_code_image)

    result = CliRunner().invoke(
        main,
        [
            "login",
            "qr-link",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--artifact",
            str(artifact),
            "--receipt",
            str(receipt_path),
            "--output",
            "json",
            "-I",
        ],
    )

    payload = _json(result)
    login_url = "https://www.zhihu.com/signin?login_method=qr"
    assert calls == [(login_url, artifact)]
    assert payload["status"] == "CHECKPOINT_LINK_READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_url"] == login_url
    assert payload["artifact_path"] == str(artifact)
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    assert receipt == payload
    assert receipt_path.stat().st_mode & 0o077 == 0
    lower = receipt_path.read_text(encoding="utf-8").lower() + result.output.lower()
    assert "cookie" not in lower
    assert "token" not in lower
    assert "phone" not in lower
    assert "code" not in lower


def test_login_qr_image_writes_ready_receipt_without_sensitive_values(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    artifact = tmp_path / "qr.png"
    ready_receipt = tmp_path / "qr-ready.json"
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_wait_for_login(
        config,
        timeout,
        *,
        method="qr",
        checkpoint_artifact=None,
        checkpoint_callback=None,
    ):
        calls.append((config, timeout, method, checkpoint_artifact))
        checkpoint_artifact.write_bytes(b"PNG")
        checkpoint_callback(
            {
                "status": "CHECKPOINT_IMAGE_READY",
                "login_method": method,
                "artifact_path": str(checkpoint_artifact),
                "artifact_mime": "image/png",
            }
        )
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "login",
            "qr-image",
            "zhihu@zhihu-test",
            "--registry",
            str(registry),
            "--artifact",
            str(artifact),
            "--ready-receipt",
            str(ready_receipt),
            "--timeout",
            "120",
            "--output",
            "json",
            "-I",
        ],
    )

    payload = _json(result)
    assert calls == [(("config", tmp_path / "runner.toml"), 120, "qr", artifact)]
    assert payload["status"] == "READY"
    assert payload["target"] == "zhihu@zhihu-test"
    assert payload["login_url"] == "https://www.zhihu.com/signin?login_method=qr"
    assert artifact.read_bytes() == b"PNG"
    receipt = json.loads(ready_receipt.read_text(encoding="utf-8"))
    assert receipt == {
        "artifact_mime": "image/png",
        "artifact_path": str(artifact),
        "login_method": "qr",
        "login_url": "https://www.zhihu.com/signin?login_method=qr",
        "status": "CHECKPOINT_IMAGE_READY",
        "target": "zhihu@zhihu-test",
    }
    lower = ready_receipt.read_text(encoding="utf-8").lower() + result.output.lower()
    assert "cookie" not in lower
    assert "token" not in lower
    assert "phone" not in lower


def test_login_code_dispatches_sms_code_checkpoint_without_phone_or_code(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "load_runner_config", lambda path: ("config", Path(path)))

    def fake_wait_for_login(config, timeout, *, method="qr"):
        calls.append((config, timeout, method))
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(cli, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
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


def test_login_code_help_does_not_accept_phone_or_verification_code_values():
    result = CliRunner().invoke(main, ["login", "code", "--help"])

    assert result.exit_code == 0
    assert "--phone" not in result.output
    assert "--code" not in result.output
    assert "verification-code" not in result.output.lower()


def test_post_draft_dispatches_create_and_writes_receipt(monkeypatch, tmp_path):
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
            "post",
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
