from pathlib import Path

from chatenv import EnvStore, get_paths

from chatpost.config import ChatpostConfig, load_csdn_credentials


def test_chatpost_chatenv_schema_registers_csdn_sensitive_fields():
    fields = ChatpostConfig.get_fields()

    assert "CHATPOST_CSDN_PHONE" in fields
    assert "CHATPOST_CSDN_USERNAME" in fields
    assert "CHATPOST_CSDN_PASSWORD" in fields
    assert fields["CHATPOST_CSDN_PHONE"].is_sensitive is True
    assert fields["CHATPOST_CSDN_USERNAME"].is_sensitive is True
    assert fields["CHATPOST_CSDN_PASSWORD"].is_sensitive is True


def test_load_csdn_credentials_reads_named_chatpost_chatenv_profile(tmp_path: Path):
    store = EnvStore(get_paths(tmp_path).envs_dir)
    store.save_profile(
        ChatpostConfig,
        "csdn-test",
        {
            "CHATPOST_CSDN_PHONE": "19900000000",
            "CHATPOST_CSDN_USERNAME": "csdn-user@example.invalid",
            "CHATPOST_CSDN_PASSWORD": "secret-password",
        },
    )

    credentials = load_csdn_credentials(profile="csdn-test", home=tmp_path)

    assert credentials.profile == "csdn-test"
    assert credentials.phone == "19900000000"
    assert credentials.username == "csdn-user@example.invalid"
    assert credentials.login_name == "csdn-user@example.invalid"
    assert credentials.password == "secret-password"
    assert credentials.has_sms_login is True
    assert credentials.has_password_login is True
    assert credentials.env_path == store.profile_path(ChatpostConfig, "csdn-test")


def test_load_csdn_credentials_uses_phone_as_login_name_when_username_missing(tmp_path: Path):
    store = EnvStore(get_paths(tmp_path).envs_dir)
    store.save_profile(
        ChatpostConfig,
        "csdn-phone-only",
        {
            "CHATPOST_CSDN_PHONE": "19900000000",
            "CHATPOST_CSDN_PASSWORD": "secret-password",
        },
    )

    credentials = load_csdn_credentials(profile="csdn-phone-only", home=tmp_path)

    assert credentials.username == "19900000000"
    assert credentials.login_name == "19900000000"
