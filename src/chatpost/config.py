"Typed environment configuration for ChatPost."

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from chatenv import BaseEnvConfig, EnvField, EnvStore, get_paths


@dataclass(frozen=True)
class CSDNCredentials:
    """CSDN login credentials loaded from ChatPost's ChatEnv provider."""

    phone: str = ""
    username: str = ""
    password: str = ""
    profile: str = "active"
    env_path: Path | None = None

    @property
    def login_name(self) -> str:
        return self.username or self.phone

    @property
    def has_password_login(self) -> bool:
        return bool(self.login_name and self.password)

    @property
    def has_sms_login(self) -> bool:
        return bool(self.phone)


class ChatpostConfig(BaseEnvConfig):
    "ChatPost ChatEnv configuration."

    _title = "ChatPost Configuration"
    _aliases = ["chatpost"]
    _storage_dir = "Chatpost"

    @classmethod
    def test(cls) -> None:
        """Validate schema registration without external side effects."""

        print(f"Testing {cls._title}...")
        print("Schema loaded; no network test is required.")

    CHATPOST_API_KEY = EnvField(
        "CHATPOST_API_KEY",
        desc="API key",
        is_sensitive=True,
    )
    CHATPOST_CSDN_PHONE = EnvField(
        "CHATPOST_CSDN_PHONE",
        desc="CSDN phone number for SMS/manual login.",
        is_sensitive=True,
    )
    CHATPOST_CSDN_USERNAME = EnvField(
        "CHATPOST_CSDN_USERNAME",
        desc="CSDN username/email/phone for password-form login.",
        is_sensitive=True,
    )
    CHATPOST_CSDN_PASSWORD = EnvField(
        "CHATPOST_CSDN_PASSWORD",
        desc="CSDN password for password-form login.",
        is_sensitive=True,
    )


def get_store(home: str | Path | None = None) -> EnvStore:
    """Return the ChatEnv store used by ChatPost."""

    return EnvStore(get_paths(home).envs_dir)


def _values_to_csdn_credentials(
    values: dict[str, Any],
    *,
    profile: str,
    env_path: Path | None,
) -> CSDNCredentials:
    phone = str(values.get("CHATPOST_CSDN_PHONE") or "")
    username = str(values.get("CHATPOST_CSDN_USERNAME") or "")
    return CSDNCredentials(
        phone=phone,
        username=username or phone,
        password=str(values.get("CHATPOST_CSDN_PASSWORD") or ""),
        profile=profile,
        env_path=env_path,
    )


def load_csdn_credentials(
    profile: str | None = None,
    home: str | Path | None = None,
) -> CSDNCredentials:
    """Load CSDN credentials from ChatPost's ChatEnv provider."""

    store = get_store(home)
    if profile:
        env_path = store.profile_path(ChatpostConfig, profile)
        values = store.load_profile(ChatpostConfig, profile)
        return _values_to_csdn_credentials(values, profile=profile, env_path=env_path)
    env_path = store.active_path(ChatpostConfig)
    values = store.load_active(ChatpostConfig)
    return _values_to_csdn_credentials(values, profile="active", env_path=env_path)


__all__ = [
    "CSDNCredentials",
    "ChatpostConfig",
    "get_store",
    "load_csdn_credentials",
]
