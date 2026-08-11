"""CLI entrypoint for chatpost."""

from __future__ import annotations

import base64
import binascii
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from chatpost import __version__
from chatpost.accounts import Account, AccountRegistryError, load_accounts, resolve_account
from chatpost.qr import generate_qr_code_image
from chatpost.csdn import (
    browser_login as csdn_browser_login,
    browser_logout as csdn_browser_logout,
    browser_status as csdn_browser_status,
    create_draft as csdn_create_draft,
    load_browser_config as load_csdn_browser_config,
)
from chatpost.xhs import (
    browser_login as xhs_browser_login,
    browser_logout as xhs_browser_logout,
    browser_status as xhs_browser_status,
    load_browser_config as load_xhs_browser_config,
)
from chatpost.zhihu import (
    RESULT_UNKNOWN,
    ResultUnknownError,
    browser_login,
    browser_logout,
    browser_status,
    execute_task,
    load_browser_config,
    load_runner_config,
)

_OUTPUT = click.Choice(["text", "json"])

_CLI_TREE_LINES = (
    "chatpost  # browser-level platform login and draft manager",
    "├── --help  # Show help for the current command.",
    "├── --version  # Show package version.",
    "├── --tree  # Print the registered CLI tree with command purpose and IO shape.",
    "├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.",
    "├── profiles [--platform zhihu|xhs|csdn] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.",
    "├── zhihu  # Zhihu browser login and Wechatsync draft capabilities",
    "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.",
    "    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.",
    "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.",
    "    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.",
    "    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or create one Zhihu draft through Wechatsync; never final-publish.",
    "├── xhs  # XHS browser login system",
    "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured XHS browser Profiles.",
    "    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--qrcode PATH] [--output text|json] [-I/--no-interactive]  # Wait for the creator login page's own QR handoff and write the QR artifact.",
    "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check XHS web login state from page-visible browser state only.",
    "    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear XHS browser state after browser-level status.",
    "└── csdn  # CSDN browser login and draft system",
    "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured CSDN browser Profiles.",
    "    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--qrcode PATH] [--output text|json] [-I/--no-interactive]  # Wait for the CSDN login page's own QR handoff and write the QR artifact.",
    "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check CSDN web login state from page-visible browser state only.",
    "    ├── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear CSDN browser state after browser-level status.",
    "    └── draft PROFILE SOURCE [--registry PATH] [--dry-run] [--receipt PATH] [--output text|json] [-I/--no-interactive]  # Dry-run or save one CSDN browser editor draft; never final-publish.",
)
_CLI_TREE_COMMAND_PATHS = (
    ("platforms",),
    ("profiles",),
    ("zhihu",),
    ("zhihu", "profiles"),
    ("zhihu", "login"),
    ("zhihu", "status"),
    ("zhihu", "logout"),
    ("zhihu", "draft"),
    ("xhs",),
    ("xhs", "profiles"),
    ("xhs", "login"),
    ("xhs", "status"),
    ("xhs", "logout"),
    ("csdn",),
    ("csdn", "profiles"),
    ("csdn", "login"),
    ("csdn", "status"),
    ("csdn", "logout"),
    ("csdn", "draft"),
)


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    click.echo(f"status: {payload.get('status', 'UNKNOWN')}")
    if payload.get("platforms"):
        for platform in payload["platforms"]:
            click.echo(f"platform: {platform.get('name')}")
            for key in ("profiles_command", "login_command", "status_command", "logout_command", "draft_command"):
                if platform.get(key):
                    click.echo(f"{key}: {platform[key]}")
    if payload.get("profiles"):
        for profile in payload["profiles"]:
            target = f"{profile.get('platform')}@{profile.get('alias')}"
            label = f" ({profile['label']})" if profile.get("label") else ""
            click.echo(f"profile: {target}{label}")
    for key in (
        "event",
        "target",
        "profile",
        "platform",
        "check_method",
        "login_url",
        "handoff_kind",
        "qrcode_path",
        "account_name",
        "account_url",
        "logout_method",
        "browser_attachment",
        "browser_version",
        "draft_id",
        "review_url",
        "source_sha256",
        "preview",
        "reason",
        "cleanup_status",
        "extension_cleanup_status",
        "adapter_cleanup_status",
    ):
        if payload.get(key):
            click.echo(f"{key}: {payload[key]}")


def _write_receipt(path: Path, payload: dict[str, Any]) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.",
        suffix=".tmp",
        dir=destination.parent,
        text=True,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
        os.chmod(destination, 0o600)
    finally:
        temporary.unlink(missing_ok=True)


def _emit_json_line(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _write_data_url_artifact(data_url: str, destination: Path) -> Path:
    if not data_url.startswith("data:image/") or "," not in data_url:
        raise click.ClickException("invalid XHS QR artifact data URL")
    header, encoded = data_url.split(",", 1)
    if ";base64" not in header.lower():
        raise click.ClickException("XHS QR artifact must be base64 encoded")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as error:
        raise click.ClickException("invalid XHS QR artifact payload") from error
    output = destination.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=output.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
        os.chmod(temporary, 0o600)
        os.replace(temporary, output)
        os.chmod(output, 0o600)
    finally:
        temporary.unlink(missing_ok=True)
    return output


def _qr_login_payload_for_emit(payload: dict[str, Any], qrcode_path: Path | None) -> dict[str, Any]:
    event = dict(payload)
    data_url = event.pop("qrcode_data_url", None)
    login_url = event.pop("login_url", None)
    wrote_qr = False
    if isinstance(data_url, str) and data_url and qrcode_path is not None:
        event["qrcode_path"] = str(_write_data_url_artifact(data_url, qrcode_path))
        wrote_qr = True
    elif isinstance(login_url, str) and login_url.strip() and qrcode_path is not None:
        artifact = generate_qr_code_image(login_url.strip(), qrcode_path)
        event["qrcode_path"] = str(artifact["artifact_path"])
        wrote_qr = True
    if wrote_qr:
        event["handoff_kind"] = "qrcode_image"
    return event


def _xhs_login_payload_for_emit(payload: dict[str, Any], qrcode_path: Path | None) -> dict[str, Any]:
    return _qr_login_payload_for_emit(payload, qrcode_path)


def _csdn_login_payload_for_emit(payload: dict[str, Any], qrcode_path: Path | None) -> dict[str, Any]:
    return _qr_login_payload_for_emit(payload, qrcode_path)


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
                "draft_command": "chatpost zhihu draft PROFILE SOURCE",
            },
            {
                "name": "xhs",
                "profiles_command": "chatpost xhs profiles",
                "login_command": "chatpost xhs login PROFILE",
                "status_command": "chatpost xhs status PROFILE",
                "logout_command": "chatpost xhs logout PROFILE",
            },
            {
                "name": "csdn",
                "profiles_command": "chatpost csdn profiles",
                "login_command": "chatpost csdn login PROFILE",
                "status_command": "chatpost csdn status PROFILE",
                "logout_command": "chatpost csdn logout PROFILE",
                "draft_command": "chatpost csdn draft PROFILE SOURCE",
            },
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


def _platform_account_or_click_error(registry: Path | None, target: str, platform: str):
    accounts = _accounts_or_click_error(registry)
    requested_platform: str | None = None
    lookup = target
    if "@" in target:
        requested_platform, lookup = target.split("@", 1)
        if requested_platform != platform:
            raise click.ClickException(
                f"target platform {requested_platform!r} does not match command platform {platform!r}"
            )
    try:
        account = resolve_account(target, accounts)
    except AccountRegistryError as alias_error:
        matches = [
            account
            for account in accounts.values()
            if account.platform == platform and account.profile == lookup
        ]
        if not matches:
            raise click.ClickException(str(alias_error)) from alias_error
        if len(matches) > 1:
            raise click.ClickException(f"ambiguous {platform} profile: {lookup}")
        account = matches[0]
        return Account(
            alias=lookup,
            platform=account.platform,
            runner_config=account.runner_config,
            profile=account.profile,
            label=account.label,
            login_methods=account.login_methods,
        )
    if account.platform != platform:
        raise click.ClickException(f"unsupported account platform: {account.platform}")
    return account


def _zhihu_account_or_click_error(registry: Path | None, target: str):
    return _platform_account_or_click_error(registry, target, "zhihu")


def _xiaohongshu_account_or_click_error(registry: Path | None, target: str):
    return _platform_account_or_click_error(registry, target, "xhs")


def _csdn_account_or_click_error(registry: Path | None, target: str):
    return _platform_account_or_click_error(registry, target, "csdn")


def _load_zhihu_browser_config(account):
    try:
        return load_browser_config(account.runner_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _load_zhihu_runner_config(account):
    try:
        return load_runner_config(account.runner_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _load_xhs_browser_config(account):
    try:
        return load_xhs_browser_config(account.runner_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _load_csdn_browser_config(account):
    try:
        return load_csdn_browser_config(account.runner_config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


def _target_context(account) -> dict[str, str]:
    return {
        "target": account.target(),
        "profile": account.alias,
        "platform": account.platform,
    }


def _with_target(account, payload: dict[str, Any]) -> dict[str, Any]:
    return {**_target_context(account), **payload}


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
    """ChatPost browser login and draft command line interface."""

    if show_tree:
        click.echo(_render_cli_tree(ctx.command))
        ctx.exit()


@main.command("platforms")
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def platforms_command(output: str, no_interactive: bool) -> None:
    """List supported platforms."""

    del no_interactive
    _emit(_platforms_payload(), output)


@main.command("profiles")
@click.option("--platform", type=click.Choice(["zhihu", "xhs", "csdn"]), default=None)
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def profiles_command(
    platform: str | None,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """List configured browser Profiles without reading login state."""

    del no_interactive
    _emit(_profiles_payload(registry, platform=platform), output)


@main.group("zhihu")
def zhihu_group() -> None:
    """Run Zhihu browser login/status/logout and draft operations."""


@zhihu_group.command("profiles")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_profiles_command(registry: Path | None, output: str, no_interactive: bool) -> None:
    """List configured Zhihu browser Profiles."""

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
    """Check PROFILE's Zhihu web login state from browser-visible page state."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_browser_config(account)
    try:
        payload = browser_status(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@zhihu_group.command("login")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_login_command(
    profile: str,
    registry: Path | None,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Open/check a pure browser login session and emit a page-owned handoff."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_browser_config(account)

    def event_callback(payload: dict[str, Any]) -> None:
        event = _with_target(account, payload)
        if output == "json":
            _emit_json_line(event)
        else:
            _emit(event, output)

    try:
        payload = browser_login(config, timeout=timeout, event_callback=event_callback)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = _with_target(account, payload)
    if output == "json":
        _emit_json_line(result)
    else:
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
    """Log out or clear PROFILE's Zhihu browser state after browser-level status."""

    del no_interactive
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_browser_config(account)
    try:
        payload = browser_logout(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@zhihu_group.command("draft")
@click.argument("profile")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, help="Validate the source through Wechatsync without starting a browser or writing.")
@click.option("--receipt", type=click.Path(path_type=Path), default=None, help="Receipt path for a real draft create. Required unless --dry-run is used.")
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def zhihu_draft_command(
    profile: str,
    source: Path,
    registry: Path | None,
    dry_run: bool,
    receipt: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Dry-run or create one Zhihu draft through Wechatsync; never final-publish."""

    del no_interactive
    if dry_run and receipt is not None:
        raise click.ClickException("--receipt is only valid when creating a draft; omit it with --dry-run")
    if not dry_run and receipt is None:
        raise click.ClickException("--receipt is required when creating a draft; pass --dry-run for validation")
    account = _zhihu_account_or_click_error(registry, profile)
    config = _load_zhihu_runner_config(account)
    mode = "dry-run" if dry_run else "create"
    try:
        payload = execute_task(config, source, mode=mode)
    except ResultUnknownError as error:
        result = _with_target(account, dict(error.receipt))
        if receipt is None:
            raise click.ClickException(str(error)) from error
        try:
            _write_receipt(receipt, result)
        except (OSError, TypeError, ValueError) as receipt_error:
            _emit(result, output)
            raise click.ClickException(
                f"{RESULT_UNKNOWN}: {error}. Receipt could not be written; do not retry automatically."
            ) from receipt_error
        raise click.ClickException(str(error)) from error
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = _with_target(account, payload)
    if not dry_run and receipt is not None:
        try:
            _write_receipt(receipt, result)
        except (OSError, TypeError, ValueError) as receipt_error:
            _emit(result, output)
            raise click.ClickException(
                "DRAFT_CREATED result was obtained, but the receipt could not be written; "
                "do not retry automatically."
            ) from receipt_error
    _emit(result, output)


@main.group("xhs")
def xiaohongshu_group() -> None:
    """Run XHS browser login/status/logout operations."""


@xiaohongshu_group.command("profiles")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def xiaohongshu_profiles_command(registry: Path | None, output: str, no_interactive: bool) -> None:
    """List configured XHS browser Profiles."""

    del no_interactive
    _emit(_profiles_payload(registry, platform="xhs"), output)


@xiaohongshu_group.command("status")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def xiaohongshu_status_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Check PROFILE's XHS web login state from browser-visible page state."""

    del no_interactive
    account = _xiaohongshu_account_or_click_error(registry, profile)
    config = _load_xhs_browser_config(account)
    try:
        payload = xhs_browser_status(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@xiaohongshu_group.command("login")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option(
    "--qrcode",
    "qrcode_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the page-owned XHS login QR image to PATH; defaults under the browser Profile.",
)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def xiaohongshu_login_command(
    profile: str,
    registry: Path | None,
    timeout: int,
    qrcode_path: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Open/check a pure browser login session and emit a page-owned handoff."""

    del no_interactive
    account = _xiaohongshu_account_or_click_error(registry, profile)
    config = _load_xhs_browser_config(account)
    qrcode_destination = qrcode_path
    if qrcode_destination is None:
        profile_dir = getattr(config, "profile_dir", None)
        if profile_dir is not None:
            qrcode_destination = Path(profile_dir) / "artifacts" / "xhs-login-qrcode.png"

    def event_callback(payload: dict[str, Any]) -> None:
        event = _with_target(account, _xhs_login_payload_for_emit(payload, qrcode_destination))
        if output == "json":
            _emit_json_line(event)
        else:
            _emit(event, output)

    try:
        payload = xhs_browser_login(config, timeout=timeout, event_callback=event_callback)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = _with_target(account, _xhs_login_payload_for_emit(payload, qrcode_destination))
    if output == "json":
        _emit_json_line(result)
    else:
        _emit(result, output)


@xiaohongshu_group.command("logout")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def xiaohongshu_logout_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Log out or clear PROFILE's XHS browser state after browser-level status."""

    del no_interactive
    account = _xiaohongshu_account_or_click_error(registry, profile)
    config = _load_xhs_browser_config(account)
    try:
        payload = xhs_browser_logout(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@main.group("csdn")
def csdn_group() -> None:
    """Run CSDN browser login/status/logout operations."""


@csdn_group.command("profiles")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def csdn_profiles_command(registry: Path | None, output: str, no_interactive: bool) -> None:
    """List configured CSDN browser Profiles."""

    del no_interactive
    _emit(_profiles_payload(registry, platform="csdn"), output)


@csdn_group.command("status")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def csdn_status_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Check PROFILE's CSDN web login state from browser-visible page state."""

    del no_interactive
    account = _csdn_account_or_click_error(registry, profile)
    config = _load_csdn_browser_config(account)
    try:
        payload = csdn_browser_status(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@csdn_group.command("login")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option(
    "--qrcode",
    "qrcode_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Write the page-owned CSDN login QR image to PATH; defaults under the browser Profile.",
)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def csdn_login_command(
    profile: str,
    registry: Path | None,
    timeout: int,
    qrcode_path: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Open/check a pure browser login session and emit a page-owned handoff."""

    del no_interactive
    account = _csdn_account_or_click_error(registry, profile)
    config = _load_csdn_browser_config(account)
    qrcode_destination = qrcode_path
    if qrcode_destination is None:
        profile_dir = getattr(config, "profile_dir", None)
        if profile_dir is not None:
            qrcode_destination = Path(profile_dir) / "artifacts" / "csdn-login-qrcode.png"

    def event_callback(payload: dict[str, Any]) -> None:
        event = _with_target(account, _csdn_login_payload_for_emit(payload, qrcode_destination))
        if output == "json":
            _emit_json_line(event)
        else:
            _emit(event, output)

    try:
        payload = csdn_browser_login(config, timeout=timeout, event_callback=event_callback)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = _with_target(account, _csdn_login_payload_for_emit(payload, qrcode_destination))
    if output == "json":
        _emit_json_line(result)
    else:
        _emit(result, output)


@csdn_group.command("logout")
@click.argument("profile")
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def csdn_logout_command(
    profile: str,
    registry: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Log out or clear PROFILE's CSDN browser state after browser-level status."""

    del no_interactive
    account = _csdn_account_or_click_error(registry, profile)
    config = _load_csdn_browser_config(account)
    try:
        payload = csdn_browser_logout(config)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _emit(_with_target(account, payload), output)


@csdn_group.command("draft")
@click.argument("profile")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--registry", type=click.Path(path_type=Path), default=None)
@click.option("--dry-run", is_flag=True, help="Validate the source without starting a browser or writing.")
@click.option("--receipt", type=click.Path(path_type=Path), default=None, help="Receipt path for a real CSDN draft save. Required unless --dry-run is used.")
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def csdn_draft_command(
    profile: str,
    source: Path,
    registry: Path | None,
    dry_run: bool,
    receipt: Path | None,
    output: str,
    no_interactive: bool,
) -> None:
    """Dry-run or save one CSDN browser editor draft; never final-publish."""

    del no_interactive
    if dry_run and receipt is not None:
        raise click.ClickException("--receipt is only valid when creating a draft; omit it with --dry-run")
    if not dry_run and receipt is None:
        raise click.ClickException("--receipt is required when creating a draft; pass --dry-run for validation")
    account = _csdn_account_or_click_error(registry, profile)
    config = _load_csdn_browser_config(account)
    try:
        payload = csdn_create_draft(config, source, dry_run=dry_run)
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    result = _with_target(account, payload)
    if not dry_run and receipt is not None:
        try:
            _write_receipt(receipt, result)
        except (OSError, TypeError, ValueError) as receipt_error:
            _emit(result, output)
            raise click.ClickException(
                "CSDN draft result was obtained, but the receipt could not be written; do not retry automatically."
            ) from receipt_error
    _emit(result, output)


if __name__ == "__main__":
    main()
