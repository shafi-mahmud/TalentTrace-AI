"""Official async PostgreSQL checkpoint lifecycle, independent of business data."""

import asyncio
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from app.core.config import Settings, settings


CONNECTION_TIMEOUT_SECONDS = 15


class CheckpointerError(RuntimeError):
    """Controlled infrastructure failure without connection or state details."""


@asynccontextmanager
async def open_checkpointer(
    configuration: Settings | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open and close one saver; callers own the compatible async event loop.

    No setup is implicit. Keep the context open for the graph's entire execution.
    Business records and SQLAlchemy sessions are never used by the saver.
    """
    active = configuration if configuration is not None else settings
    if active.langgraph_checkpoint_database_url is None:
        raise CheckpointerError("Checkpoint storage is not configured.")
    serializer = JsonPlusSerializer(
        allowed_msgpack_modules=None, allowed_json_modules=None, pickle_fallback=False,
    )
    # Separate opening/closing errors from caller workflow errors: the latter
    # must keep their original type and semantics (including interruptions).
    try:
        manager = AsyncPostgresSaver.from_conn_string(
            active.langgraph_checkpoint_database_url.get_secret_value(), serde=serializer,
        )
        saver = await asyncio.wait_for(
            manager.__aenter__(), timeout=CONNECTION_TIMEOUT_SECONDS,
        )
    except Exception:
        raise CheckpointerError("Checkpoint connection could not be opened.") from None
    try:
        yield saver
    finally:
        try:
            await manager.__aexit__(None, None, None)
        except Exception:
            raise CheckpointerError("Checkpoint connection could not be closed.") from None


async def setup_checkpointer(configuration: Settings | None = None) -> None:
    """Explicitly run LangGraph-owned setup/migrations, never TalentTrace Alembic."""
    try:
        async with open_checkpointer(configuration) as saver:
            await saver.setup()
    except CheckpointerError:
        raise
    except Exception:
        raise CheckpointerError("Checkpoint initialization failed.") from None
