"""CLI entrypoint for chatpost."""

from __future__ import annotations

import json
import tempfile
import time
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
    logout as logout_from_zhihu,
    preflight,
    wait_for_login,
)

_OUTPUT = click.Choice(["text", "json"])

_CLI_TREE_LINES = (
    "chatpost  # platform content publishing and draft orchestration",
    "├── --help  # Show help for the current command.",
    "├── --version  # Show package version.",
    "├── --tree  # Print the registered CLI tree with command purpose and IO shape.",
    "├── platforms [--output text|json] [-I/--no-interactive]  # List supported publishing platforms.",
    "├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Chrome/profile targets.",
    "└── zhihu  # Zhihu platform capabilities",
    "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu Chrome/profile targets.",
    "    ├── login PROFILE [--registry PATH] [--qr PATH] [--receipt PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open live QR login, emit link/QR/receipt, and wait for READY.",
    "    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Clear Zhihu login state for this profile; does not read session values.",
    "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Read-only Zhihu auth check.",
    "    └── draft  # Zhihu review-draft operations",
    "        ├── dry-run PROFILE SOURCE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Parse SOURCE without starting browser or writing Zhihu.",
    "        └── create PROFILE SOURCE [--registry PATH] --receipt PATH [--output text|json] [-I/--no-interactive]  # Create exactly one Zhihu review draft.",
)
_CLI_TREE_COMMAND_PATHS = (
    ("platforms",),
    ("profiles",),
    ("zhihu",),
    ("zhihu", "profiles"),
    ("zhihu", "login"),
    ("zhihu", "logout"),
    ("zhihu", "status"),
    ("zhihu", "draft"),
    ("zhihu", "draft", "dry-run"),
    ("zhihu", "draft", "create"),
)


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    click.echo(f"status: {payload.get('status', 'UNKNOWN')}")
    if payload.get("platforms"):
        for platform in payload["platforms"]:
            click.echo(f"platform: {platform.get('name')}")
            for key in ("profiles_command", "login_command", "status_command", "logout_command"):
                if platform.get(key):
                    click.echo(f"{key}: {platform[key]}")
    if payload.get("profiles"):
        for profile in payload["profiles"]:
            target = f"{profile.get('platform')}@{profile.get('alias')}"
            label = f" ({profile['label']})" if profile.get("label") else ""
            click.echo(f"profile: {target}{label}")
    for key in (
        "target",
        "platform",
        "login_method",
        "login_url",
        "artifact_path",
        "receipt_path",
        "checkpoint_artifact_path",
        "artifact_mime",
        "data_length",
        "qr_expires_at",
        "logout_method",
        "draft_id",
        "review_url",
    ):
        if payload.get(key):
            click.echo(f"{key}: {payload[key]}")


def _platforms_payload() -> dict[str, Any]:
    return {
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


def _profiles_payload(registry: Path | None, *, platform: str | None = None) -> dict[str, Any]:
    accounts = _accounts_or_click_error(registry)
    profiles = [
        account.to_payload()
        for account in accounts.values()
        if platform is None or account.platform == platform
    ]
    payload: dict[str, Any] = {"status": "READY", "profiles": profiles}
    if platform is not None:
        payload["platform"] = platform
    return payload


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


@main.command("platforms")
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def platforms_command(output: str, no_interactive: bool) -> None:
    """List supported publishing platforms."""

    del no_interactive
    _emit(_platforms_payload(), output)


@main.command("profiles")
@click.option("--platform", type=click.Choice(["zhihu"]), default=None)
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def profiles_command(
    platform: str | None,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """List configured Chrome/profile targets without reading session values."""

    del no_interactive
    _emit(_profiles_payload(registry, platform=platform), output)


@main.group("account", hidden=True)
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


@main.group("qr", hidden=True)
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
    """Run Zhihu login, profile status, and draft operations."""


@zhihu_group.command("profiles")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_profiles_command(registry: Path | None, output: str, no_interactive: bool) -> None:
    """List configured Zhihu Chrome/profile targets."""

    del no_interactive
    _emit(_profiles_payload(registry, platform="zhihu"), output)


@zhihu_group.command("status")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_status_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Perform a read-only Zhihu auth check for PROFILE."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_runner_config(account)
    try:
        payload = execute_task(config, None, mode="auth")
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


def _default_login_qr_path(account) -> Path:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return Path.cwd() / f"chatpost-{account.platform}-{account.alias}-login-{stamp}.png"


@zhihu_group.command("login")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--qr", "qr_path", type=click.Path(path_type=Path), default=None)
@click.option("--receipt", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_login_command(
    profile: str,
    registry: Path | None,
    qr_path: Path | None,
    receipt: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open live QR login, emit link/QR/receipt, and wait for READY."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_runner_config(account)
    qr_path = qr_path or _default_login_qr_path(account)
    receipt = receipt or qr_path.with_suffix(".json")
    checkpoint_payload: dict[str, Any] = {}

    def checkpoint_callback(payload: dict[str, Any]) -> None:
        checkpoint_payload.clear()
        checkpoint_payload.update({"target": account.target(), **payload})
        checkpoint_payload["receipt_path"] = str(receipt.expanduser().resolve())
        _write_receipt(receipt, checkpoint_payload)

    try:
        payload = wait_for_login(
            config,
            timeout=timeout,
            method="qr",
            checkpoint_artifact=qr_path,
            checkpoint_callback=checkpoint_callback,
        )
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = {"target": account.target(), **payload}
    for key in ("login_url", "artifact_path", "artifact_mime", "data_length", "receipt_path"):
        if checkpoint_payload.get(key) and not result.get(key):
            result[key] = checkpoint_payload[key]
    _emit(result, output)


@zhihu_group.command("logout")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_logout_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Clear Zhihu login state for PROFILE without reading session values."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_runner_config(account)
    try:
        payload = logout_from_zhihu(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit({"target": account.target(), **payload}, output)


@zhihu_group.group("account", hidden=True)
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
@click.option("--artifact", type=click.Path(path_type=Path), default=None)
@click.option("--receipt", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_account_login_qr_command(
    target: str,
    registry: Path | None,
    artifact: Path | None,
    receipt: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open a Zhihu QR checkpoint and wait for a successful auth check."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, target)
    config = _load_zhihu_runner_config(account)
    if receipt is not None and artifact is None:
        raise click.ClickException("--receipt requires --artifact")
    checkpoint_callback = None
    if receipt is not None:
        def checkpoint_callback(payload: dict[str, Any]) -> None:
            payload = {"target": account.target(), **payload}
            payload["receipt_path"] = str(receipt.expanduser().resolve())
            _write_receipt(receipt, payload)
    try:
        payload = wait_for_login(
            config,
            timeout=timeout,
            method="qr",
            checkpoint_artifact=artifact,
            checkpoint_callback=checkpoint_callback,
        )
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
