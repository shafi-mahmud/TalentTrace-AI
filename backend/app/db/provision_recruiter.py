"""Local administrator command. Credentials are prompted, never command-line arguments."""
import asyncio
from getpass import getpass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import hash_password, session_factory
from app.core.config import ConfigurationError
from app.db.models.recruiter import Recruiter
from app.api.routers.auth import LoginRequest


async def provision():
    email = input("Recruiter email: ").strip().casefold()
    password = getpass("Password (15–128 characters): ")
    if not 15 <= len(password) <= 128 or password != getpass("Confirm password: "):
        print("Password length or confirmation is invalid.")
        return
    LoginRequest(email=email, password=password)
    async with session_factory()() as session:
        if await session.scalar(select(Recruiter.id).where(Recruiter.email == email)):
            print("Account already exists; no changes made.")
            return
        session.add(Recruiter(email=email, password_hash=hash_password(password)))
        await session.commit()
    print("Recruiter account created.")


if __name__ == "__main__":
    try:
        asyncio.run(provision())
    except (ConfigurationError, ValueError, SQLAlchemyError, OSError):
        print("Provisioning failed; check configuration and migration readiness.")
