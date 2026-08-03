from click.testing import CliRunner

import chatpost.commands.zhihu as command
from chatpost.cli import main


def test_zhihu_cli_exposes_only_proven_task_commands():
    zhihu = main.commands["zhihu"]
    assert set(zhihu.commands) == {"preflight", "login", "auth", "draft"}
    assert set(zhihu.commands["draft"].commands) == {"dry-run", "create"}


def test_preflight_json(monkeypatch, tmp_path):
    config = tmp_path / "runner.toml"
    config.write_text("[zhihu]\n", encoding="utf-8")
    monkeypatch.setattr(command, "load_runner_config", lambda _path: object())
    monkeypatch.setattr(command, "preflight", lambda _config: {"status": "READY"})

    result = CliRunner().invoke(
        main,
        ["zhihu", "preflight", "--config", str(config), "--output", "json", "-I"],
    )

    assert result.exit_code == 0
    assert '"status": "READY"' in result.output


def test_login_cli_dispatches_read_only_checkpoint(monkeypatch, tmp_path):
    config = tmp_path / "runner.toml"
    config.write_text("[zhihu]", encoding="utf-8")
    sentinel = object()
    calls = []
    monkeypatch.setattr(command, "load_runner_config", lambda _path: sentinel)
    monkeypatch.setattr(
        command,
        "wait_for_login",
        lambda loaded, timeout: calls.append((loaded, timeout)) or {"status": "READY"},
    )

    result = CliRunner().invoke(
        main,
        [
            "zhihu",
            "login",
            "--config",
            str(config),
            "--timeout",
            "60",
            "--output",
            "json",
            "-I",
        ],
    )

    assert result.exit_code == 0
    assert calls == [(sentinel, 60)]
    assert '"status": "READY"' in result.output


def test_create_writes_safe_receipt(monkeypatch, tmp_path):
    config = tmp_path / "runner.toml"
    source = tmp_path / "article.md"
    receipt = tmp_path / "receipt.json"
    config.write_text("[zhihu]\n", encoding="utf-8")
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
            "create",
            str(source),
            "--config",
            str(config),
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
    assert "token" not in receipt.read_text(encoding="utf-8").lower()
