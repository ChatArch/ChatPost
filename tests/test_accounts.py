import json
from pathlib import Path

import pytest

from chatpost.accounts import AccountRegistryError, load_accounts


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
