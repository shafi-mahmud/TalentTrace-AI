"""Lazy server-side configuration with controlled, secret-free failures."""

from pathlib import Path
import re
from urllib.parse import urlsplit

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
WEBHOOK_PATH = re.compile(r"/api/(?:v10/)?webhooks/[0-9]{17,20}/[A-Za-z0-9_-]{32,200}")


class PublishingConfigurationError(RuntimeError):
    """Safe configuration failure; never contains the submitted secret."""


class Settings(BaseSettings):
    discord_webhook_url: SecretStr | None = None

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
        frozen=True,
    )

    @field_validator("discord_webhook_url", mode="before")
    @classmethod
    def validate_webhook(cls, value: object) -> SecretStr | None:
        if value is None:
            return None
        try:
            raw = value.get_secret_value() if isinstance(value, SecretStr) else value
            if not isinstance(raw, str) or len(raw) > 400:
                raise ValueError
            # Reject whitespace, escaped delimiters, ports, userinfo and query strings.
            if any(ord(char) <= 32 or ord(char) >= 127 for char in raw):
                raise ValueError
            url = urlsplit(raw)
            if (
                url.scheme != "https"
                or url.netloc not in {"discord.com", "discordapp.com"}
                or not WEBHOOK_PATH.fullmatch(url.path)
                or url.query
                or url.fragment
                or "?" in raw
                or "#" in raw
            ):
                raise ValueError
            return SecretStr(raw)
        except Exception:
            raise PublishingConfigurationError(
                "Discord publishing configuration is invalid."
            ) from None

    def require_webhook(self) -> SecretStr:
        if self.discord_webhook_url is None:
            raise PublishingConfigurationError(
                "Discord publishing is not configured."
            )
        return self.discord_webhook_url


def load_settings() -> Settings:
    """Environment overrides the ignored root .env; import does not read it."""
    try:
        return Settings()
    except Exception:
        raise PublishingConfigurationError(
            "Discord publishing configuration could not be loaded."
        ) from None
