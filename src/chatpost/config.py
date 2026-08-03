"Typed environment configuration for ChatPost."

from chatenv import BaseEnvConfig, EnvField


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


__all__ = ["ChatpostConfig"]
