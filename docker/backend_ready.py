"""Read-only liveness + current-schema readiness. Never migrate or log settings."""
import asyncio
import sys
from urllib.request import urlopen

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text

# Executed from /app/backend by both health checks and operator verification.
sys.path.insert(0, '/app/backend')
from app.db.session import create_database_engine


async def ready():
    with urlopen('http://127.0.0.1:8000/api/v1/health', timeout=2) as response:
        if response.status != 200:
            return False
    expected = ScriptDirectory.from_config(Config('alembic.ini')).get_current_head()
    engine = create_database_engine()
    try:
        async with engine.connect() as connection:
            revisions = (await connection.execute(text('SELECT version_num FROM alembic_version'))).scalars().all()
            return revisions == [expected]
    finally:
        await engine.dispose()


if __name__ == '__main__':
    try:
        ok = asyncio.run(ready())
    except Exception:
        ok = False
    # Only fixed safe output is retained in Docker health diagnostics.
    print('ready' if ok else 'not ready: check explicit migration and database readiness')
    sys.exit(0 if ok else 1)
