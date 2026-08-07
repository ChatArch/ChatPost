import json
from pathlib import Path

import pytest

from chatpost.accounts import (
    AccountRegistryError,
    default_chatpost_home,
    default_registry_path,
    load_accounts,
)


def _registry_toml(runner: Path) -> str:
    return (
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
    )


def test_default_paths_live_under_chatarch_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("CHATPOST_HOME", raising=False)
    monkeypatch.delenv("CHATPOST_ACCOUNT_REGISTRY", raising=False)

    assert default_chatpost_home() == tmp_path / ".chatarch" / "chatpost"
    assert default_registry_path() == tmp_path / ".chatarch" / "chatpost" / "accounts.toml"


def test_default_registry_honors_chatpost_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    state_root = tmp_path / "chatarch-state" / "chatpost"
    monkeypatch.setenv("CHATPOST_HOME", str(state_root))
    monkeypatch.delenv("CHATPOST_ACCOUNT_REGISTRY", raising=False)

    assert default_chatpost_home() == state_root.resolve()
    assert default_registry_path() == state_root.resolve() / "accounts.toml"


def test_account_registry_override_wins(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    state_root = tmp_path / "chatpost-home"
    registry = tmp_path / "registries" / "accounts.toml"
    monkeypatch.setenv("CHATPOST_HOME", str(state_root))
    monkeypatch.setenv("CHATPOST_ACCOUNT_REGISTRY", str(registry))

    assert default_registry_path() == registry.resolve()


def test_load_accounts_uses_default_registry_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    runner = tmp_path / "runner.toml"
    registry = tmp_path / "accounts.toml"
    registry.write_text(_registry_toml(runner), encoding="utf-8")
    monkeypatch.setenv("CHATPOST_ACCOUNT_REGISTRY", str(registry))

    account = load_accounts()["zhihu-test"]

    assert account.runner_config == runner.resolve()


def test_load_accounts_accepts_non_sensitive_login_methods_and_relative_runner(tmp_path: Path):
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-qr-login"]\n'
        'platform = "zhihu"\n'
        'runner_config = "runner-qr-login.toml"\n'
        'profile = "zhihu-qr-login"\n'
        'label = "QR login practice account"\n'
        'login_methods = ["qr"]\n',
        encoding="utf-8",
    )

    account = load_accounts(registry)["zhihu-qr-login"]

    assert account.runner_config == (tmp_path / "runner-qr-login.toml").resolve()
    assert account.login_methods == ("qr",)
    assert account.to_payload() == {
        "alias": "zhihu-qr-login",
        "platform": "zhihu",
        "runner_config": str((tmp_path / "runner-qr-login.toml").resolve()),
        "profile": "zhihu-qr-login",
        "label": "QR login practice account",
        "login_methods": ["qr"],
    }


@pytest.mark.parametrize(
    ("toml", "message"),
    [
        ('login_methods = "qr"\n', "login_methods must be a string list"),
        ('login_methods = ["password"]\n', "unsupported login method"),
    ],
)
def test_load_accounts_rejects_invalid_login_methods(tmp_path: Path, toml: str, message: str):
    runner = tmp_path / "runner.toml"
    registry = tmp_path / "accounts.toml"
    registry.write_text(
        '[accounts."zhihu-test"]\n'
        'platform = "zhihu"\n'
        f'runner_config = {json.dumps(str(runner))}\n'
        + toml,
        encoding="utf-8",
    )

    with pytest.raises(AccountRegistryError, match=message):
        load_accounts(registry)
