import json
from pathlib import Path

import click
from click.testing import CliRunner

import chatpost.cli as command
from chatpost.cli import main
from chatpost.zhihu import RESULT_UNKNOWN, ResultUnknownError


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


def test_zhihu_cli_exposes_profile_based_task_commands_with_hidden_compatibility():
    zhihu = main.commands["zhihu"]
    assert {"profiles", "login", "logout", "status", "draft"}.issubset(zhihu.commands)
    assert zhihu.commands["profiles"].hidden is False
    assert zhihu.commands["login"].hidden is False
    assert zhihu.commands["logout"].hidden is False
    assert zhihu.commands["status"].hidden is False
    assert zhihu.commands["draft"].hidden is False
    assert not isinstance(zhihu.commands["draft"], click.Group)

    assert "account" in zhihu.commands
    assert zhihu.commands["account"].hidden is True
    assert set(zhihu.commands["account"].commands) == {"preflight", "status", "login"}
    assert set(zhihu.commands["account"].commands["login"].commands) == {
        "qr",
        "qr-artifact",
        "code",
    }


def test_preflight_json(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "preflight",
        lambda config: calls.append(config) or {"status": "READY"},
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

    assert result.exit_code == 0, result.output
    assert calls == [sentinel]
    assert '"status": "READY"' in result.output
    assert '"target": "zhihu@zhihu-test"' in result.output


def test_status_json_dispatches_read_only_auth(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
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

    assert result.exit_code == 0, result.output
    assert calls == [(sentinel, None, "auth")]
    assert '"status": "READY"' in result.output
    assert '"target": "zhihu@zhihu-test"' in result.output


def test_login_cli_dispatches_single_qr_handoff(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    qr_path = tmp_path / "login.png"
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)

    def fake_wait_for_login(
        loaded,
        *,
        timeout,
        method="qr",
        checkpoint_artifact=None,
        checkpoint_callback=None,
    ):
        calls.append((loaded, timeout, method, checkpoint_artifact, checkpoint_callback))
        return {"status": "READY", "login_method": method}

    monkeypatch.setattr(command, "wait_for_login", fake_wait_for_login)

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "login",
            "zhihu-test",
            "--registry",
            str(registry),
            "--qr",
            str(qr_path),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )

    assert result.exit_code == 0, result.output
    assert calls == [(sentinel, 60, "qr", qr_path, calls[0][4])]
    assert '"status": "READY"' in result.output
    assert '"login_method": "qr"' in result.output


def test_create_writes_safe_receipt(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    receipt = tmp_path / "receipt.json"
    source.write_text("# title", encoding="utf-8")
    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())
    monkeypatch.setattr(
        command,
        "execute_task",
        lambda *_args, **_kwargs: {
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

    assert result.exit_code == 0, result.output
    assert receipt.is_file()
    assert "DRAFT_CREATED" in receipt.read_text(encoding="utf-8")
    assert "zhihu@zhihu-test" in receipt.read_text(encoding="utf-8")
    assert "token" not in receipt.read_text(encoding="utf-8").lower()


def test_unknown_receipt_write_failure_preserves_do_not_retry_result(
    monkeypatch, tmp_path
):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    receipt = tmp_path / "receipt.json"
    source.write_text("# title", encoding="utf-8")
    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())

    def ambiguous(*_args, **_kwargs):
        raise ResultUnknownError(
            "adapter result is ambiguous; do not retry automatically",
            receipt={
                "status": RESULT_UNKNOWN,
                "cleanup_status": "CLOSED",
                "adapter_cleanup_status": "MANUAL_RECOVERY_REQUIRED",
            },
        )

    monkeypatch.setattr(command, "execute_task", ambiguous)
    monkeypatch.setattr(
        command,
        "_write_receipt",
        lambda *_args: (_ for _ in ()).throw(OSError("receipt unavailable")),
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

    assert result.exit_code != 0
    assert RESULT_UNKNOWN in result.output
    assert "MANUAL_RECOVERY_REQUIRED" in result.output
    assert "receipt could not be written" in result.output.lower()
    assert "do not retry automatically" in result.output.lower()


def test_created_result_is_emitted_before_receipt_write_failure(monkeypatch, tmp_path):
    registry = _registry(tmp_path)
    source = tmp_path / "article.md"
    receipt = tmp_path / "receipt.json"
    source.write_text("# title", encoding="utf-8")
    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())
    monkeypatch.setattr(
        command,
        "execute_task",
        lambda *_args, **_kwargs: {
            "status": "DRAFT_CREATED",
            "draft_id": "2067000000000000001",
            "review_url": "https://zhuanlan.zhihu.com/p/2067000000000000001/edit",
            "source_sha256": "abc",
        },
    )
    monkeypatch.setattr(
        command,
        "_write_receipt",
        lambda *_args: (_ for _ in ()).throw(OSError("receipt unavailable")),
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

    assert result.exit_code != 0
    assert '"status": "DRAFT_CREATED"' in result.output
    assert "receipt could not be written" in result.output.lower()
    assert "do not retry automatically" in result.output.lower()
