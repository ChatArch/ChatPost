"""CLI entrypoint for chatpost."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

from chatpost import __version__
from chatpost.accounts import AccountRegistryError, load_accounts, resolve_account
from chatpost.zhihu import (
    browser_login,
    browser_logout,
    browser_status,
    load_browser_config,
)

_OUTPUT = click.Choice(["text", "json"])

_CLI_TREE_LINES = (
    "chatpost  # browser-level platform login manager",
    "├── --help  # Show help for the current command.",
    "├── --version  # Show package version.",
    "├── --tree  # Print the registered CLI tree with command purpose and IO shape.",
    "├── platforms [--output text|json] [-I/--no-interactive]  # List supported platforms without starting a browser.",
    "├── profiles [--platform zhihu] [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured browser Profiles without checking login state.",
    "└── zhihu  # Zhihu browser login capabilities",
    "    ├── profiles [--registry PATH] [--output text|json] [-I/--no-interactive]  # List configured Zhihu browser Profiles.",
    "    ├── login PROFILE [--registry PATH] [--timeout INTEGER] [--output text|json] [-I/--no-interactive]  # Open/check a pure browser login session; emit page-owned login_url if needed.",
    "    ├── status PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Check Zhihu web login state from page-visible browser state only.",
    "    └── logout PROFILE [--registry PATH] [--output text|json] [-I/--no-interactive]  # Log out or clear Zhihu browser state after browser-level status.",
)
_CLI_TREE_COMMAND_PATHS = (
    ("platforms",),
    ("profiles",),
    ("zhihu",),
    ("zhihu", "profiles"),
    ("zhihu", "login"),
    ("zhihu", "status"),
    ("zhihu", "logout"),
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
        "event",
        "target",
        "profile",
        "platform",
        "check_method",
        "login_url",
        "handoff_kind",
        "account_name",
        "account_url",
        "logout_method",
        "browser_attachment",
        "browser_version",
    ):
        if payload.get(key):
            click.echo(f"{key}: {payload[key]}")


def _emit_json_line(payload: dict[str, Any]) -> None:
    click.echo(json.dumps(payload, ensure_ascii=False, sort_keys=True))


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


def _load_zhihu_browser_config(account):
    try:
        return load_browser_config(account.runner_config)
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
    """ChatPost browser-login command line interface."""

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
    """List configured browser Profiles without reading login state."""

    del no_interactive
    _emit(_profiles_payload(registry, platform=platform), output)


@main.group("zhihu")
def zhihu_group() -> None:
    """Run pure browser-level Zhihu login/status/logout operations."""


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


if __name__ == "__main__":
    main()
