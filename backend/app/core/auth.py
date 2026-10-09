"""Opaque revocable sessions; passwords and bearer cookies are never logged."""
import hashlib
import hmac
import secrets
from datetime import datetime, timezone
from functools import lru_cache
from urllib.parse import urlsplit

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import ConfigurationError, settings
from app.db.session import create_database_engine, create_database_session_factory
from app.db.models.recruiter import Recruiter, RecruiterSession

COOKIE_NAME = "talenttrace_session"


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    value = hashlib.scrypt(password.encode(), salt=salt, n=2**17, r=8, p=1, maxmem=256 * 1024 * 1024)
    return "scrypt$" + salt.hex() + "$" + value.hex()


def verify_password(password: str, encoded: str) -> bool:
    try:
        method, salt, _ = encoded.split("$")
        return method == "scrypt" and len(salt) == 32 and hmac.compare_digest(hash_password(password, bytes.fromhex(salt)), encoded)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@lru_cache(maxsize=1)
def dummy_password_hash():
    return hash_password(secrets.token_urlsafe(32))


@lru_cache(maxsize=1)
def session_factory():
    return create_database_session_factory(create_database_engine())


async def database_session():
    try:
        async with session_factory()() as session:
            yield session
    except (ConfigurationError, SQLAlchemyError, OSError):
        raise HTTPException(503, "Application storage is unavailable.") from None


async def protect_mutation(request: Request):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        # A non-simple header prevents cross-site HTML forms, including login CSRF.
        if request.headers.get("x-talenttrace-request") != "1":
            raise HTTPException(403, "Request verification required.")
        origin = request.headers.get("origin")
        if origin:
            try:
                parsed = urlsplit(origin)
                permitted = parsed.scheme in {"http", "https"} and not parsed.username and not parsed.password and not parsed.path and not parsed.query and not parsed.fragment and (
                    origin in settings.cors_origins or parsed.netloc == request.headers.get("host"))
            except ValueError:
                permitted = False
            if not permitted:
                raise HTTPException(403, "Request origin is not allowed.")


async def current_recruiter(request: Request, session=Depends(database_session)) -> Recruiter:
    await protect_mutation(request)
    token = request.cookies.get(COOKIE_NAME, "")
    if len(token) != 43:
        raise HTTPException(401, "Sign in required.")
    user = await session.scalar(select(Recruiter).join(RecruiterSession).where(
        RecruiterSession.token_hash == token_hash(token),
        RecruiterSession.expires_at > datetime.now(timezone.utc), Recruiter.active.is_(True)))
    if user is None:
        raise HTTPException(401, "Sign in required.")
    request.state.recruiter_id = user.id
    return user
