import asyncio
import importlib

import asyncpg
import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.orm import DeclarativeBase

import app.core.config as config_module
from app.core.config import ConfigurationError, Settings
from app.db import base as base_module
from app.db import session as session_module


VALID_DATABASE_URL = (
    "postgresql+asyncpg://talenttrace:private-test-password@localhost:5432/"
    "talenttrace"
)


def make_settings(database_url: str | None = None) -> Settings:
    return Settings(_env_file=None, database_url=database_url)


async def get_health_response() -> httpx.Response:
    from app.main import app

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        return await client.get("/api/v1/health")


def test_application_imports_without_database_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_attempted = False
    original_settings = config_module.settings
    no_database_settings = Settings(_env_file=None, database_url=None)

    async def fail_if_connected(*args: object, **kwargs: object) -> None:
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Application import must not connect to PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", fail_if_connected)
    monkeypatch.setattr(config_module, "settings", no_database_settings)
    main_module = importlib.import_module("app.main")

    try:
        main_module = importlib.reload(main_module)

        assert main_module.settings is no_database_settings
        assert main_module.settings.database_url is None
        assert main_module.app is not None
        assert connection_attempted is False
    finally:
        config_module.settings = original_settings
        importlib.reload(main_module)


def test_database_url_is_optional() -> None:
    configuration = make_settings()

    assert configuration.database_url is None


def test_health_endpoint_remains_unaffected_without_database_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_attempted = False

    async def fail_if_connected(*args: object, **kwargs: object) -> None:
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Health endpoint must not connect to PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", fail_if_connected)
    response = asyncio.run(get_health_response())

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "talenttrace-api",
    }
    assert connection_attempted is False


def test_valid_async_postgresql_url_is_accepted() -> None:
    configuration = make_settings(VALID_DATABASE_URL)

    assert configuration.database_url is not None
    assert configuration.database_url.get_secret_value() == VALID_DATABASE_URL


@pytest.mark.parametrize(
    "database_url",
    [
        "sqlite:///talenttrace.db",
        "postgresql://user:password@localhost/talenttrace",
        "https://example.test/database",
    ],
)
def test_non_asyncpg_database_schemes_are_rejected(database_url: str) -> None:
    with pytest.raises(ConfigurationError) as captured_error:
        make_settings(database_url)

    assert database_url not in str(captured_error.value)
    assert "password" not in str(captured_error.value)


def test_database_url_is_hidden_in_normal_secret_representation() -> None:
    configuration = make_settings(VALID_DATABASE_URL)

    assert configuration.database_url is not None
    assert "private-test-password" not in str(configuration.database_url)
    assert "private-test-password" not in repr(configuration.database_url)
    assert "private-test-password" not in repr(configuration)


def test_malformed_database_url_does_not_leak_credentials() -> None:
    malformed_url = (
        "postgresql+asyncpg://talenttrace:private-test-password@[invalid/"
        "talenttrace"
    )

    with pytest.raises(ConfigurationError) as captured_error:
        make_settings(malformed_url)

    assert malformed_url not in str(captured_error.value)
    assert "private-test-password" not in str(captured_error.value)


def test_shared_base_has_no_tables() -> None:
    assert issubclass(base_module.Base, DeclarativeBase)
    assert dict(base_module.Base.metadata.tables) == {}


def test_engine_factory_requires_url_only_when_called() -> None:
    configuration = make_settings()

    with pytest.raises(ConfigurationError) as captured_error:
        session_module.create_database_engine(configuration)

    assert str(captured_error.value) == (
        "DATABASE_URL is required to create the database engine."
    )


def test_engine_factory_is_lazy_and_uses_asyncpg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_attempted = False

    async def fail_if_connected(*args: object, **kwargs: object) -> None:
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Engine creation must not connect to PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", fail_if_connected)
    engine = session_module.create_database_engine(make_settings(VALID_DATABASE_URL))

    try:
        assert isinstance(engine, AsyncEngine)
        assert engine.dialect.name == "postgresql"
        assert engine.dialect.driver == "asyncpg"
        assert engine.echo is False
        assert connection_attempted is False
    finally:
        asyncio.run(engine.dispose())


def test_session_factory_creates_session_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_attempted = False

    async def fail_if_connected(*args: object, **kwargs: object) -> None:
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Session creation must not connect to PostgreSQL")

    monkeypatch.setattr(asyncpg, "connect", fail_if_connected)
    engine = session_module.create_database_engine(make_settings(VALID_DATABASE_URL))
    session_factory = session_module.create_database_session_factory(engine)
    database_session = session_factory()

    try:
        assert isinstance(database_session, AsyncSession)
        assert database_session.bind is engine
        assert connection_attempted is False
    finally:
        asyncio.run(database_session.close())
        asyncio.run(engine.dispose())


def test_database_modules_import_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection_attempted = False

    async def fail_if_connected(*args: object, **kwargs: object) -> None:
        nonlocal connection_attempted
        connection_attempted = True
        raise AssertionError("Database module import must not connect")

    monkeypatch.setattr(asyncpg, "connect", fail_if_connected)

    importlib.reload(base_module)
    importlib.reload(session_module)

    assert connection_attempted is False
    assert not any(
        isinstance(value, AsyncEngine) for value in vars(session_module).values()
    )
    assert dict(base_module.Base.metadata.tables) == {}
