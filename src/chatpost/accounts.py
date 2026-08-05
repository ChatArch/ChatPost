"""Non-sensitive ChatPost account registry helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 CI
    import tomli as tomllib

_SENSITIVE_KEY_MARKERS = (
    "token",
    "password",
    "passwd",
    "cookie",
    "secret",
    "credential",
    "authorization",
    "api_key",
    "localstorage",
    "indexeddb",
)
_ALLOWED_ACCOUNT_KEYS = {"platform", "runner_config", "profile", "label"}


def default_registry_path() -> Path:
    """Return the default non-sensitive account registry path."""

    configured = os.environ.get("CHATPOST_ACCOUNT_REGISTRY")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path("~/.chatarch/chatpost/accounts.toml").expanduser().resolve()


@dataclass(frozen=True)
class Account:
    """A non-sensitive publishing account alias."""

    alias: str
    platform: str
    runner_config: Path
    profile: str | None = None
    label: str | None = None

    def target(self) -> str:
        return f"{self.platform}@{self.alias}"

    def to_payload(self) -> dict[str, str]:
        payload = {
            "alias": self.alias,
            "platform": self.platform,
            "runner_config": str(self.runner_config),
        }
        if self.profile:
            payload["profile"] = self.profile
        if self.label:
            payload["label"] = self.label
        return payload


class AccountRegistryError(ValueError):
    """Raised when the account registry is missing or invalid."""


def _reject_sensitive_keys(table: dict[str, Any], *, alias: str) -> None:
    for key in table:
        lowered = key.replace("-", "_").lower()
        if any(marker in lowered for marker in _SENSITIVE_KEY_MARKERS):
            raise AccountRegistryError(
                f"account {alias!r} contains sensitive field {key!r}; "
                "store only non-sensitive metadata"
            )
        if key not in _ALLOWED_ACCOUNT_KEYS:
            raise AccountRegistryError(f"account {alias!r} contains unsupported field {key!r}")


def _required_string(table: dict[str, Any], key: str, *, alias: str) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value:
        raise AccountRegistryError(f"account {alias!r} must define string field {key!r}")
    return value


def load_accounts(path: str | Path | None = None) -> dict[str, Account]:
    """Load a non-sensitive TOML registry from disk."""

    registry_path = Path(path).expanduser().resolve() if path else default_registry_path()
    try:
        with registry_path.open("rb") as stream:
            data = tomllib.load(stream)
    except OSError as error:
        raise AccountRegistryError(f"account registry is unavailable: {registry_path}") from error
    raw_accounts = data.get("accounts", {})
    if not isinstance(raw_accounts, dict):
        raise AccountRegistryError("account registry must contain an [accounts] table")
    accounts: dict[str, Account] = {}
    for alias, table in raw_accounts.items():
        if not isinstance(alias, str) or not alias:
            raise AccountRegistryError("account aliases must be non-empty strings")
        if not isinstance(table, dict):
            raise AccountRegistryError(f"account {alias!r} must be a table")
        _reject_sensitive_keys(table, alias=alias)
        platform = _required_string(table, "platform", alias=alias)
        if platform != "zhihu":
            raise AccountRegistryError(f"unsupported account platform: {platform}")
        runner_config = Path(_required_string(table, "runner_config", alias=alias)).expanduser().resolve()
        profile = table.get("profile")
        label = table.get("label")
        if profile is not None and not isinstance(profile, str):
            raise AccountRegistryError(f"account {alias!r} profile must be a string")
        if label is not None and not isinstance(label, str):
            raise AccountRegistryError(f"account {alias!r} label must be a string")
        accounts[alias] = Account(
            alias=alias,
            platform=platform,
            runner_config=runner_config,
            profile=profile,
            label=label,
        )
    return accounts


def resolve_account(target: str, accounts: dict[str, Account]) -> Account:
    """Resolve either ALIAS or PLATFORM@ALIAS."""

    if "@" in target:
        platform, alias = target.split("@", 1)
    else:
        alias = target
        platform = None
    if not alias:
        raise AccountRegistryError("target must include a non-empty account alias")
    try:
        account = accounts[alias]
    except KeyError as error:
        raise AccountRegistryError(f"unknown account alias: {alias}") from error
    if platform is not None and platform != account.platform:
        raise AccountRegistryError(
            f"target platform {platform!r} does not match account platform {account.platform!r}"
        )
    return account


__all__ = [
    "Account",
    "AccountRegistryError",
    "default_registry_path",
    "load_accounts",
    "resolve_account",
]
