from sqlalchemy.exc import ArgumentError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import ConfigurationError, Settings, settings


def create_database_engine(configuration: Settings | None = None) -> AsyncEngine:
    """Create a lazy async engine without opening a database connection."""
    active_settings = configuration or settings
    if active_settings.database_url is None:
        raise ConfigurationError(
            "DATABASE_URL is required to create the database engine."
        )

    try:
        return create_async_engine(
            active_settings.database_url.get_secret_value(),
            echo=False,
            hide_parameters=True,
        )
    except ArgumentError:
        raise ConfigurationError(
            "DATABASE_URL is not a valid SQLAlchemy database URL."
        ) from None


def create_database_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create a reusable factory for async database sessions."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
