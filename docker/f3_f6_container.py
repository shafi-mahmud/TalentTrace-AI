"""Opt-in container fixture. No Docker socket, host URL, secrets or cleanup."""
import asyncio
from io import StringIO
import os
from pathlib import Path
import re
import socket

import asyncpg
from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy.engine import URL

# Reuse the unchanged, parametrized connected test and its eight scenarios.
from test_interview_assessment_flow import (test_connected_scheduled_capture_analysis_assessment,
    no_external_inference)


def validate_project(value):
    if not re.fullmatch(r"tt-f3f6-test-[0-9a-f]{12}", value or ""):
        raise RuntimeError("Explicit isolated test project identity required")
    return value


def require_fresh(identity, consumed, populated):
    if tuple(identity) != ("transcript_test", "transcript_test", 54402):
        raise RuntimeError("Test database identity mismatch")
    if consumed or populated:
        raise RuntimeError("Database is not fresh; preserve it and use a new project")


def allowed_connection(address, addresses):
    return isinstance(address, tuple) and len(address) >= 2 and address[0] in addresses and address[1] == 54402


@pytest.fixture(autouse=True)
def database_only_network(monkeypatch):
    addresses = {item[4][0] for item in socket.getaddrinfo("db", 54402, type=socket.SOCK_STREAM)}
    original = socket.socket.connect
    def connect(sock, address):
        if not allowed_connection(address, addresses):
            raise RuntimeError("Non-database network access blocked")
        return original(sock, address)
    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect)


@pytest.fixture(scope="module")
def pg():
    if "F3_F6_TEST_PROJECT" not in os.environ:
        pytest.skip("Enable the explicit isolated Compose test workflow")
    project = validate_project(os.environ.get("F3_F6_TEST_PROJECT"))
    async def initialize():
        # Fixed service address: arbitrary database URLs are never accepted.
        connection = await asyncpg.connect(host="db", port=54402,
            user="transcript_test", database="transcript_test")
        try:
            identity = await connection.fetchrow("SELECT current_database() AS db, current_user AS usr, inet_server_port() AS port")
            require_fresh(identity.values(), False, False)
            # Includes prior lab marker, extensions and user tables: no reused DB.
            async with connection.transaction():
                await connection.execute("SELECT pg_advisory_xact_lock(734806120)")
                consumed = await connection.fetchval("SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname='f3_f6_test_owner')")
                populated = await connection.fetchval("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public')")
                require_fresh(identity.values(), consumed, populated)
                await connection.execute("CREATE SCHEMA f3_f6_test_owner; CREATE TABLE f3_f6_test_owner.marker (project text NOT NULL)")
                await connection.execute("INSERT INTO f3_f6_test_owner.marker VALUES ($1)", project)
            output = StringIO()
            cfg = Config(str(Path(__file__).parent / "alembic.ini"), output_buffer=output)
            cfg.set_main_option("script_location", str(Path(__file__).parent / "alembic"))
            command.upgrade(cfg, "0015_reviewer_confirmation", sql=True)
            await connection.execute(output.getvalue())
            assert await connection.fetchval("SELECT version_num FROM alembic_version") == "0015_reviewer_confirmation"
        finally:
            await connection.close()
    asyncio.run(initialize())
    yield URL.create("postgresql+asyncpg", username="transcript_test", host="db",
        port=54402, database="transcript_test")
    # Deliberately preserve evidence and database on success or failure.
