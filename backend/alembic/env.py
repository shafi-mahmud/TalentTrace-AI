"""PostgreSQL-only migrations; offline SQL generation needs no credentials."""

import asyncio

from alembic import context
from sqlalchemy.exc import SQLAlchemyError

from app.db.base import Base
from app.db.models import KnowledgeChunk, KnowledgeDocument  # Register both tables.


target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        dialect_name="postgresql", target_metadata=target_metadata,
        literal_binds=True, compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_on_connection(connection) -> None:
    if connection.dialect.name != "postgresql":
        raise RuntimeError("Knowledge migrations require PostgreSQL.")
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    from app.core.config import ConfigurationError
    from app.db.session import create_database_engine

    engine = None
    try:
        engine = create_database_engine()
        async with engine.connect() as connection:
            await connection.run_sync(run_migrations_on_connection)
    except (ConfigurationError, SQLAlchemyError, OSError):
        raise RuntimeError(
            "PostgreSQL migration failed; check local configuration, extension availability and permissions."
        ) from None
    finally:
        if engine is not None:
            await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
