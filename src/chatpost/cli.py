"""CLI entrypoint for chatpost."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import click

from chatpost import __version__
from chatpost.accounts import AccountRegistryError, load_accounts, resolve_account
from chatpost.qr import generate_qr_code_image
from chatpost.zhihu import (
    RESULT_UNKNOWN,
    ResultUnknownError,
    create_login_qr_artifact,
    execute_task,
    load_runner_config,
    preflight,
    wait_for_login,
)

_OUTPUT = click.Choice(["text", "json"])

_CLI_TREE_LINES = (
    "chatpost  # platform content publishing and draft orchestration",
    "├── --help  # Show help for the current command.",
    "├── --version  # Show package version.",
    "├── --tree  # Print the registered CLI tree with command purpose and IO shape.",
    "├── account  # account alias registry; metadata only",
    "│   ├── list [--registry PATH] [--output text|json] [-I/--no-interactive]  # List account aliases; never reads cookies/tokens/session.",
    "│   └── show TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Show one account alias by ALIAS or PLATFORM@ALIAS.",
    "├── qr  # platform-neutral QR artifact tools",
    "│   └── encode DATA --artifact PATH [--output text|json] [-I/--no-interactive]  # Render DATA into PNG without echoing DATA by default.",
    "└── zhihu  # Zhihu platform capabilities",
    "    ├── account  # Zhihu account status, preflight, and login checkpoints",
    "    │   ├── status TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.",
    "    │   ├── preflight TARGET [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check runner/profile/browser/extension readiness.",
    "    │   └── login  # Zhihu manual login checkpoints; no phone/code/cookie arguments.",
    "    │       ├── qr TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open QR login checkpoint and wait for READY.",
    "    │       ├── qr-artifact TARGET [--registry PATH] --artifact PATH --receipt PATH [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Create live QR PNG + receipt, return immediately.",
    "    │       └── code TARGET [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open SMS-code checkpoint without accepting phone/code values.",
    "    └── draft  # Zhihu review-draft operations",
    "        ├── dry-run TARGET SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.",
    "        └── create TARGET SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.",
)
_CLI_TREE_COMMAND_PATHS = (
    ("account",),
    ("account", "list"),
    ("account", "show"),
    ("qr",),
    ("qr", "encode"),
    ("zhihu",),
    ("zhihu", "account"),
    ("zhihu", "account", "status"),
    ("zhihu", "account", "preflight"),
    ("zhihu", "account", "login"),
    ("zhihu", "account", "login", "qr"),
    ("zhihu", "account", "login", "qr-artifact"),
    ("zhihu", "account", "login", "code"),
    ("zhihu", "draft"),
    ("zhihu", "draft", "dry-run"),
    ("zhihu", "draft", "create"),
)


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    click.echo(f"status: {payload.get('status', 'UNKNOWN')}")
    for key in (
        "target",
        "login_method",
        "login_url",
        "artifact_path",
        "receipt_path",
        "checkpoint_artifact_path",
        "artifact_mime",
        "data_length",
        "qr_expires_at",
        "draft_id",
        "review_url",
    ):
        if payload.get(key):
            click.echo(f"{key}: {payload[key]}")


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        delete=False,
    ) as stream:
        temporary = Path(stream.name)
        json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")
    try:
        temporary.chmod(0o600)
        temporary.replace(destination)
        destination.chmod(0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _accounts_or_click_error(registry: Path | None):
    try:
        return load_accounts(registry)
    except AccountRegistryError as error:
        raise click.ClickException(str(error)) from error


def _account_or_click_error(registry: Path | None, target: str):
    accounts = _accounts_or_click_error(registry)
    try:
        return resolve_account(target, accounts)
    except AccountRegistryError as error:
        raise click.ClickException(str(error)) from error


def _zhihu_account_or_click_error(registry: Path | None, target: str):
    account = _account_or_click_error(registry, target)
    if account.platform != "zhihu":
        raise click.ClickException(f"unsupported account platform: {account.platform}")
    return account


def _load_zhihu_runner_config(account):
    try:
        return load_runner_config(account.runner_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _ensure_cli_tree_matches_registered(root: click.Group) -> None:
    for path in _CLI_TREE_COMMAND_PATHS:
        current: click.Command = root
        for part in path:
            if not isinstance(current, click.Group):
                raise click.ClickException(f"CLI tree path is not registered: {' '.join(path)}")
            current = current.commands.get(part)  # type: ignore[assignment]
            if current is None:
                raise click.ClickException(f"CLI tree path is not registered: {' '.join(path)}")


def _render_cli_tree(root: click.Group) -> str:
    _ensure_cli_tree_matches_registered(root)
    return "\n".join(_CLI_TREE_LINES)


@click.group(invoke_without_command=True)
@click.version_option(__version__, prog_name="chatpost")
@click.option("--tree", "show_tree", is_flag=True, is_eager=True, help="Print the registered CLI tree.")
@click.pass_context
def main(ctx: click.Context, show_tree: bool) -> None:
    """ChatPost command line interface."""

    if show_tree:
        click.echo(_render_cli_tree(ctx.command))
        ctx.exit()


@main.group("account")
def account_group() -> None:
    """List and inspect non-sensitive ChatPost account aliases."""


@account_group.command("list")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def account_list_command(registry: Path | None, output: str, no_interactive: bool) -> None:
    """List configured account aliases without exposing credentials."""

    del no_interactive
    accounts = _accounts_or_click_error(registry)
    _emit(
        {
            "status": "READY",
            "accounts": [account.to_payload() for account in accounts.values()],
        },
        output,
    )


@account_group.command("show")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def account_show_command(
    target: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Show one account alias by ALIAS or PLATFORM@ALIAS."""

    del no_interactive
    account = _account_or_click_error(registry, target)
    _emit({"status": "READY", "account": account.to_payload()}, output)


@main.group("qr")
def qr_group() -> None:
    """Generate non-platform-specific QR code image artifacts."""


@qr_group.command("encode")
@click.argument("data")
@click.option("--artifact", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def qr_encode_command(data: str, artifact: Path, output: str, no_interactive: bool) -> None:
    """Render DATA into a PNG QR code without echoing DATA by default."""

    del no_interactive
    try:
        payload = generate_qr_code_image(data, artifact)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"status": "QR_CODE_READY", **payload}, output)


@main.group("zhihu")
def zhihu_group() -> None:
    """Run Zhihu platform account and draft operations."""


@zhihu_group.group("account")
def zhihu_account_group() -> None:
    """Check Zhihu account state and open login checkpoints."""


@zhihu_account_group.command("status")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_status_command(
    target: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Perform a read-only Zhihu auth check for TARGET."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = execute_task(config, None, mode="auth")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_account_group.command("preflight")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_preflight_command(
    target: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Check runner/profile/browser/extension readiness for TARGET."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = preflight(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_account_group.group("login")
def zhihu_account_login_group() -> None:
    """Open Zhihu manual login checkpoints."""


@zhihu_account_login_group.command("qr")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_login_qr_command(
    target: str,
    registry: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open a Zhihu QR checkpoint and wait for a successful auth check."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = wait_for_login(config, timeout=timeout, method="qr")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_account_login_group.command("qr-artifact")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--artifact", type=click.Path(path_type=Path), required=True)
@click.option("--receipt", type=click.Path(path_type=Path), required=True)
@click.option("--timeout", type=click.IntRange(min=1), default=60, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_login_qr_artifact_command(
    target: str,
    registry: Path | None,
    artifact: Path,
    receipt: Path,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Create a live Zhihu QR PNG and receipt, then return immediately."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = {
            "target": account.target(),
            **create_login_qr_artifact(config, artifact, timeout=timeout),
        }
        payload["receipt_path"] = str(receipt.expanduser().resolve())
        _write_receipt(receipt, payload)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(payload, output)


@zhihu_account_login_group.command("code")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_login_code_command(
    target: str,
    registry: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open a Zhihu SMS-code checkpoint without accepting phone/code values."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = wait_for_login(config, timeout=timeout, method="code")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_group.group("draft")
def zhihu_draft_group() -> None:
    """Create or validate Zhihu review drafts."""


@zhihu_draft_group.command("dry-run")
@click.argument("target")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_draft_dry_run_command(
    target: str,
    source: Path,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Parse SOURCE for TARGET without starting a browser or writing Zhihu."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = execute_task(config, source, mode="dry-run")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_draft_group.command("create")
@click.argument("target")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--receipt", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_draft_create_command(
    target: str,
    source: Path,
    registry: Path | None,
    receipt: Path,
    output: str,
    no_interactive: bool,
) -> None:
    """Create exactly one Zhihu review draft for TARGET from SOURCE."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    try:
        payload = execute_task(config, source, mode="create")
    except ResultUnknownError as error:
        receipt_payload = {"target": account.target(), **error.receipt}
        try:
            _write_receipt(receipt, receipt_payload)
        except (OSError, TypeError, ValueError):
            _emit(receipt_payload, output)
            raise click.ClickException(
                f"{RESULT_UNKNOWN}: {error}. Receipt could not be written; "
                "do not retry automatically."
            ) from error
        raise click.ClickException(str(error)) from error
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    payload = {"target": account.target(), **payload}
    try:
        _write_receipt(receipt, payload)
    except (OSError, TypeError, ValueError) as receipt_error:
        _emit(payload, output)
        raise click.ClickException(
            "DRAFT_CREATED result was obtained, but the receipt could not be written; "
            "do not retry automatically."
        ) from receipt_error
    _emit(payload, output)


if __name__ == "__main__":
    main()
