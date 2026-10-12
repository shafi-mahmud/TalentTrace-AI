from pathlib import Path
from typing import Annotated, Any
from urllib.parse import unquote, urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, StringConstraints, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from app.core.urls import validate_application_url


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
    application_form_url: SecretStr | None = None
    cv_upload_root: Path = REPOSITORY_ROOT / "data" / "cv_uploads"
    ocr_tessdata_path: Path | None = None
    langgraph_checkpoint_database_url: SecretStr | None = None
    company_policy_document_id: UUID | None = None
    groq_api_key: SecretStr | None = None
    livekit_url: SecretStr | None = None
    livekit_api_key: SecretStr | None = None
    livekit_api_secret: SecretStr | None = None
    livekit_synthetic_demo_enabled: bool = False
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

    @field_validator("application_form_url")
    @classmethod
    def validate_form_url(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            validate_application_url(value.get_secret_value())
        return value

    def model_post_init(self, __context: Any) -> None:
        if self.langgraph_checkpoint_database_url is not None:
            try:
                from psycopg.conninfo import conninfo_to_dict

                checkpoint_url = self.langgraph_checkpoint_database_url.get_secret_value()
                parsed = urlsplit(checkpoint_url)
                if parsed.scheme != "postgresql" or parsed.fragment:
                    raise ValueError("Invalid checkpoint URL")
                info = conninfo_to_dict(checkpoint_url)
                if info.get("port") and any(
                    not port.isdigit() or not 1 <= int(port) <= 65535
                    for port in info["port"].split(",")
                ):
                    raise ValueError("Invalid checkpoint port")
                if not info.get("dbname") or "service" in info:
                    raise ValueError("An explicit checkpoint database is required")
            except Exception:
                raise ConfigurationError(
                    "Checkpoint configuration requires a valid postgresql URL with an explicit database."
                ) from None
            if self.database_url is not None:
                try:
                    business_name = unquote(urlsplit(self.database_url.get_secret_value()).path.lstrip("/"))
                except ValueError:
                    raise ConfigurationError("Database configuration could not be validated.") from None
                if info["dbname"] == business_name:
                    raise ConfigurationError("Checkpoint storage must use a separate database.")
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
