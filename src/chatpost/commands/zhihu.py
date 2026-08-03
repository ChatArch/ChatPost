"""Task-oriented Zhihu commands."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

import click

from chatpost.zhihu import (
    ResultUnknownError,
    execute_task,
    load_runner_config,
    preflight,
    wait_for_login,
)

_OUTPUT = click.Choice(["text", "json"])


def _emit(payload: dict[str, Any], output: str) -> None:
    if output == "json":
        click.echo(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return
    click.echo(f"status: {payload.get('status', 'UNKNOWN')}")
    for key in (
        "playwright_version",
        "browser_revision",
        "browser_version",
        "draft_id",
        "review_url",
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


def _run_or_click_error(call):
    try:
        return call()
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error


@click.group("zhihu")
def zhihu_group() -> None:
    """Run the proven Playwright + Wechatsync Zhihu draft route."""


@zhihu_group.command("preflight")
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def preflight_command(config_path: Path, output: str, no_interactive: bool) -> None:
    """Validate exact browser, Profile, extension, adapter and loopback ports."""

    del no_interactive
    payload = _run_or_click_error(lambda: preflight(load_runner_config(config_path)))
    _emit(payload, output)


@zhihu_group.command("login")
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--timeout", type=click.IntRange(min=1), default=900, show_default=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def login_command(
    config_path: Path,
    timeout: int,
    output: str,
    no_interactive: bool,
) -> None:
    """Keep the Profile open while waiting for a manual Zhihu login."""

    del no_interactive
    payload = _run_or_click_error(
        lambda: wait_for_login(load_runner_config(config_path), timeout=timeout)
    )
    _emit(payload, output)


@zhihu_group.command("auth")
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def auth_command(config_path: Path, output: str, no_interactive: bool) -> None:
    """Start the exact Runner and perform a read-only Zhihu auth check."""

    del no_interactive
    payload = _run_or_click_error(
        lambda: execute_task(load_runner_config(config_path), None, mode="auth")
    )
    _emit(payload, output)


@click.group("draft")
def draft_group() -> None:
    """Dry-run or create one Zhihu draft. Final publish is not available."""


@draft_group.command("dry-run")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def dry_run_command(
    source: Path,
    config_path: Path,
    output: str,
    no_interactive: bool,
) -> None:
    """Parse one source through Wechatsync without starting a browser or writing."""

    del no_interactive
    payload = _run_or_click_error(
        lambda: execute_task(load_runner_config(config_path), source, mode="dry-run")
    )
    _emit(payload, output)


@draft_group.command("create")
@click.argument("source", type=click.Path(path_type=Path))
@click.option("--config", "config_path", type=click.Path(path_type=Path), required=True)
@click.option("--receipt", type=click.Path(path_type=Path), required=True)
@click.option("--output", type=_OUTPUT, default="text", show_default=True)
@click.option("-I", "--no-interactive", is_flag=True, help="Fail instead of prompting.")
def create_command(
    source: Path,
    config_path: Path,
    receipt: Path,
    output: str,
    no_interactive: bool,
) -> None:
    """Create exactly one draft; never retry an ambiguous write."""

    del no_interactive
    try:
        payload = execute_task(load_runner_config(config_path), source, mode="create")
    except ResultUnknownError as error:
        _write_receipt(receipt, error.receipt)
        raise click.ClickException(str(error)) from error
    except (OSError, RuntimeError, TypeError, ValueError) as error:
        raise click.ClickException(str(error)) from error
    _write_receipt(receipt, payload)
    _emit(payload, output)


zhihu_group.add_command(draft_group)

__all__ = ["zhihu_group"]
