"""CLI entrypoint for chatpost."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import click

from chatpost import __version__
from chatpost.accounts import AccountRegistryError, load_accounts, resolve_account
from chatpost.commands.zhihu import zhihu_group
from chatpost.zhihu import (
    RESULT_UNKNOWN,
    ResultUnknownError,
    execute_task,
    load_runner_config,
    wait_for_login,
)

_OUTPUT = click.Choice(["text", "json"])


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    click.echo(f"status: {payload.get('status', 'UNKNOWN')}")
    for key in ("target", "draft_id", "review_url"):
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


def _unsupported_platform(account) -> click.ClickException:
    return click.ClickException(f"unsupported account platform: {account.platform}")


@click.group()
@click.version_option(__version__, prog_name="chatpost")
def main() -> None:
    """chatpost command line interface."""


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


@main.group("login")
def login_group() -> None:
    """Run account login checkpoints and read-only status checks."""


@login_group.command("status")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def login_status_command(
    target: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Perform a read-only account auth check."""

    del no_interactive
    account = _account_or_click_error(registry, target)
    if account.platform != "zhihu":
        raise _unsupported_platform(account)
    try:
        payload = execute_task(load_runner_config(account.runner_config), None, mode="auth")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@login_group.command("qr")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def login_qr_command(
    target: str,
    registry: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open the account login checkpoint and wait for readiness."""

    del no_interactive
    account = _account_or_click_error(registry, target)
    if account.platform != "zhihu":
        raise _unsupported_platform(account)
    try:
        payload = wait_for_login(load_runner_config(account.runner_config), timeout=timeout)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@login_group.command("code")
@click.argument("target")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def login_code_command(
    target: str,
    registry: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open a Zhihu SMS-code login checkpoint without storing phone/code values."""

    del no_interactive
    account = _account_or_click_error(registry, target)
    if account.platform != "zhihu":
        raise _unsupported_platform(account)
    try:
        payload = wait_for_login(
            load_runner_config(account.runner_config),
            timeout=timeout,
            method="code",
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@main.group("post")
def post_group() -> None:
    """Create platform review drafts from source posts."""


@post_group.command("draft")
@click.argument("target")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--receipt", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def post_draft_command(
    target: str,
    source: Path,
    registry: Path | None,
    receipt: Path,
    output: str,
    no_interactive: bool,
) -> None:
    """Create exactly one review draft for TARGET from SOURCE."""

    del no_interactive
    account = _account_or_click_error(registry, target)
    if account.platform != "zhihu":
        raise _unsupported_platform(account)
    try:
        payload = execute_task(load_runner_config(account.runner_config), source, mode="create")
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


main.add_command(zhihu_group)


if __name__ == "__main__":
    main()
