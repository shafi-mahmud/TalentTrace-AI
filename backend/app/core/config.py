from pathlib import Path
from typing import Annotated, Any
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints
from pydantic_settings import BaseSettings, SettingsConfigDict


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
LLMModelName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=200,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$",
    ),
]


class ConfigurationError(RuntimeError):
    """Raised when application configuration cannot be used safely."""


class Settings(BaseSettings):
    app_name: str = "TalentTrace AI"
    environment: str = "development"
    api_v1_prefix: str = "/api/v1"
    database_url: SecretStr | None = None
    company_policy_document_id: UUID | None = None
    groq_api_key: SecretStr | None = None
    llm_model: LLMModelName = "openai/gpt-oss-120b"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    model_config = SettingsConfigDict(
        env_file=REPOSITORY_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    def model_post_init(self, __context: Any) -> None:
        if self.database_url is None:
            return

        database_url = self.database_url.get_secret_value()
        try:
            scheme = urlsplit(database_url).scheme.lower()
        except ValueError:
            raise ConfigurationError(
                "DATABASE_URL must be a valid postgresql+asyncpg URL."
            ) from None

        if scheme != "postgresql+asyncpg":
            raise ConfigurationError(
                "DATABASE_URL must use the postgresql+asyncpg scheme."
            )


settings = Settings()
